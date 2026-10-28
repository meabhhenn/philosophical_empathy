"""readBook.py — one-time loader that chunks the books and fills the Chroma database.

Run this ONCE to populate chroma_db. After that, main.py just opens the database.

Build order (so each stage can be checked):
  Steps 1-3 (current): open file, strip Gutenberg boilerplate, split into paragraphs.
  Steps 4-5 (next):     drop too-short pieces, break up too-long pieces.
  Steps 6-7 (last):     id + metadata, add to collection in batches with progress.
"""


def load_text(path):
    """Step 1: open a book file and return its full text."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def strip_gutenberg(text):
    """Step 2: cut off everything before '*** START' and after '*** END'."""
    start_marker = "*** START OF THE PROJECT GUTENBERG"
    end_marker = "*** END OF THE PROJECT GUTENBERG"

    start = text.find(start_marker)
    if start != -1:
        # skip to the end of the START marker line
        start = text.find("\n", start) + 1
        text = text[start:]

    end = text.find(end_marker)
    if end != -1:
        text = text[:end]

    return text.strip()


def split_paragraphs(text):
    """Step 3: split on blank lines into paragraphs; collapse internal newlines."""
    raw = text.split("\n\n")
    paragraphs = []
    for piece in raw:
        # join wrapped lines inside a paragraph into a single line, tidy whitespace
        cleaned = " ".join(piece.split())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


MIN_WORDS = 20    # skip anything shorter than this (headings, labels, junk)
MAX_WORDS = 150   # break anything longer than this into smaller chunks
                  # (model caps at 256-piece inputs, and old English uses
                  #  more sub-word pieces per word, so keep a safe margin)


def _split_into_sentences(text):
    """Rough sentence splitter: break after . ! ? followed by a space."""
    sentences = []
    current = ""
    for i, ch in enumerate(text):
        current += ch
        if ch in ".!?" and i + 1 < len(text) and text[i + 1] == " ":
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return sentences


def _hard_wrap(text):
    """Fallback: split on word count when a single sentence exceeds MAX_WORDS."""
    words = text.split()
    return [" ".join(words[i:i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]


def chunk_paragraph(paragraph):
    """Step 5: break a too-long paragraph into <= MAX_WORDS chunks on sentence boundaries."""
    if len(paragraph.split()) <= MAX_WORDS:
        return [paragraph]

    chunks = []
    current = []
    count = 0
    for sentence in _split_into_sentences(paragraph):
        n = len(sentence.split())
        if n > MAX_WORDS:
            # a single sentence too long to fit: flush, then hard-wrap it
            if current:
                chunks.append(" ".join(current))
                current, count = [], 0
            chunks.extend(_hard_wrap(sentence))
            continue
        if count + n > MAX_WORDS and current:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += n
    if current:
        chunks.append(" ".join(current))

    # merge a too-short trailing chunk back into the previous one,
    # but only if the merged result still fits under MAX_WORDS
    if len(chunks) >= 2 and len(chunks[-1].split()) < MIN_WORDS:
        merged = chunks[-2] + " " + chunks[-1]
        if len(merged.split()) <= MAX_WORDS:
            chunks[-2] = merged
            chunks.pop()
    return chunks


def make_chunks(paragraphs):
    """Steps 4-5: drop too-short pieces, split too-long ones."""
    chunks = []
    for p in paragraphs:
        if len(p.split()) < MIN_WORDS:
            continue  # step 4: skip headings and other short junk
        for c in chunk_paragraph(p):  # step 5: break up long paragraphs
            if len(c.split()) >= MIN_WORDS:
                chunks.append(c)  # also drop tiny fragments left by splitting
    return chunks


# One config entry per book: file, id prefix, and metadata.
BOOKS = [
    {
        "path": "texts_clean/meditations.txt",
        "prefix": "marcus",
        "author": "Marcus Aurelius",
        "work": "Meditations",
    },
    {
        "path": "texts_clean/essays.txt",
        "prefix": "montaigne",
        "author": "Michel de Montaigne",
        "work": "Essays, Book 1",
    },
    {
        "path": "texts_clean/minor_dialogues.txt",
        "prefix": "seneca",
        "author": "Seneca",
        "work": "Minor Dialogues",
    },
]

BATCH_SIZE = 500  # how many chunks to send to Chroma per add() call


def build_records(book):
    """Steps 1-6: read a book and return parallel lists of documents, ids, metadatas."""
    text = strip_gutenberg(load_text(book["path"]))
    chunks = make_chunks(split_paragraphs(text))

    documents, ids, metadatas = [], [], []
    for i, chunk in enumerate(chunks):
        documents.append(chunk)
        ids.append(f"{book['prefix']}-{i:04d}")  # e.g. marcus-0001
        metadatas.append({
            "author": book["author"],
            "work": book["work"],
            "type": "book",
        })
    return documents, ids, metadatas


def add_in_batches(collection, documents, ids, metadatas, label):
    """Step 7: add records to the collection in batches, printing progress."""
    total = len(documents)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        collection.add(
            documents=documents[start:end],
            ids=ids[start:end],
            metadatas=metadatas[start:end],
        )
        print(f"  {label}: added {end}/{total} chunks")


if __name__ == "__main__":
    import chromadb

    # Same database location and collection name that main.py reads from.
    client = chromadb.PersistentClient(path="chroma_db")

    # Open (or create) the collection without wiping it. Journal entries and
    # anything else that isn't a book must survive a reload.
    collection = client.get_or_create_collection(name="philosophy")

    # Build everything first. If any file fails to read/parse, we bail out here
    # BEFORE deleting anything, so the existing books stay intact.
    built = []
    for book in BOOKS:
        print(f"\nLoading {book['work']} by {book['author']} ...")
        documents, ids, metadatas = build_records(book)
        print(f"  {len(documents)} chunks built")
        built.append((book, documents, ids, metadatas))

    # Every file loaded successfully. Now it's safe to remove the old book
    # chunks, leaving journal entries (and any other non-book type) untouched.
    print("\nAll books built successfully. Removing old book chunks ...")
    collection.delete(where={"type": "book"})

    # Add the freshly built book chunks.
    for book, documents, ids, metadatas in built:
        print(f"\nAdding {book['work']} by {book['author']} ...")
        print(f"  {len(documents)} chunks to add")
        add_in_batches(collection, documents, ids, metadatas, book["prefix"])

    print(f"\nDone. Collection 'philosophy' now holds {collection.count()} chunks.")