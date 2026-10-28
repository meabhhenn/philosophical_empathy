"""main.py — a journaling companion backed by philosophy.

Flow for a new entry:
  1. Ask gpt-4o-mini to name the feelings in the entry in one short sentence.
  2. Show that sentence as "What I'm hearing:".
  3. Search each philosopher with the FEELINGS sentence (not the raw entry).
  4. Show matching passages as "<Philosopher> felt something like this too:"
     with a one-line note on who they were (no distance labels).
  5. Save the entry (plus its feelings sentence) in a separate "journal"
     collection, kept apart from the "philosophy" collection of book chunks.

The OpenAI key is loaded from a .env file via python-dotenv (OPENAI_API_KEY).
"""

import datetime
import os
import time

import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # pull OPENAI_API_KEY (and anything else) out of .env

AUTHORS = ["Marcus Aurelius", "Seneca", "Michel de Montaigne"]

# One-line note on who each philosopher was, keyed by stored author value.
AUTHOR_BIOS = {
    "Marcus Aurelius": "a Roman emperor who wrote private Stoic notes to himself.",
    "Seneca": "a Roman Stoic statesman, playwright, and letter-writer.",
    "Michel de Montaigne": "a 16th-century French thinker who invented the essay.",
}

# Distance cutoffs (smaller = closer).
MAX_DISTANCE = 1.55     # philosopher-passage match
JOURNAL_DISTANCE = 1.3  # stricter cutoff for echoing a past journal entry

CHAT_MODEL = "gpt-4o-mini"


# --------------------------------------------------------------------------- #
# collections
# --------------------------------------------------------------------------- #
def get_collection():
    """Open the philosophy collection that readBook.py populates."""
    client = chromadb.PersistentClient(path="chroma_db")
    return client.get_or_create_collection(name="philosophy")


def get_journal_collection():
    """Open (or create) the separate collection that holds journal entries."""
    client = chromadb.PersistentClient(path="chroma_db")
    return client.get_or_create_collection(name="journal")


def add_journal_entry(journal, text, feelings=""):
    """Save a journal entry to the journal collection.

    Stores the entry text as the document, with metadata holding today's date
    and the feelings sentence (so it can be shown later). The id is based on
    the current timestamp so each entry is unique. Returns the id used.
    """
    entry_id = f"journal-{time.time_ns()}"  # nanosecond timestamp -> unique id
    today = datetime.date.today().isoformat()
    journal.add(
        documents=[text],
        ids=[entry_id],
        metadatas=[{"type": "journal", "date": today, "feelings": feelings}],
    )
    return entry_id


# --------------------------------------------------------------------------- #
# OpenAI: name the feelings
# --------------------------------------------------------------------------- #
def name_feelings(entry):
    """Ask gpt-4o-mini for one short sentence naming the feelings in `entry`.

    Returns the sentence, or None if the model couldn't be reached.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("(No OPENAI_API_KEY found in .env — can't name feelings.)")
        return None
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You read a journal entry and reply with ONE "
                        "first-person sentence that describes, in plain "
                        "everyday words, what the person is going through and "
                        "the situation behind it. Do NOT use the words "
                        "\"feeling\", \"feelings\", \"emotion\", or "
                        "\"emotions\". Do NOT name specific people, places, or "
                        "events; use general words instead (e.g. \"someone "
                        "close to me\" rather than \"my sister\", or \"a "
                        "setback\" rather than \"midterms\"). No advice, no "
                        "preamble — just the sentence. "
                        "Example: \"I feel cut off from the people I count on, "
                        "right when everything is going wrong.\""
                    ),
                },
                {"role": "user", "content": entry},
            ],
            temperature=0.3,
            max_tokens=60,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:  # network/auth/quota issues shouldn't crash the app
        print(f"(Couldn't reach OpenAI: {exc})")
        return None


# --------------------------------------------------------------------------- #
# philosopher search
# --------------------------------------------------------------------------- #
def _print_author_match(collection, author, query, n_results=1):
    """Query one author with `query`; print the closest in-cutoff passage.

    Returns True if a passage was printed.
    """
    res = collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"author": author},
    )
    docs = res["documents"][0]
    if not docs or res["distances"][0][0] > MAX_DISTANCE:
        return False
    work = res["metadatas"][0][0].get("work", "")
    bio = AUTHOR_BIOS.get(author, "")
    print(f"\n{author} felt something like this too:")
    print(f"  ({author} was {bio})")
    print(f"  {work}: {docs[0]}")
    return True


def reflect_on_entry(collection, journal, entry):
    """Full journal flow: name feelings, search philosophers, save the entry."""
    feelings = name_feelings(entry)
    if not feelings:
        # fall back to searching the raw entry if the model was unavailable
        feelings = entry
        print("\nWhat I'm hearing: (couldn't summarise — using your words)")
    else:
        print(f"\nWhat I'm hearing: {feelings}")

    # Search all three philosophers with the feelings sentence, then show only
    # the single closest passage overall (if it's under the cutoff).
    best = None  # (distance, author, work, document)
    for author in AUTHORS:
        res = collection.query(
            query_texts=[feelings],
            n_results=1,
            where={"author": author},
        )
        docs = res["documents"][0]
        if not docs:
            continue
        distance = res["distances"][0][0]
        if best is None or distance < best[0]:
            work = res["metadatas"][0][0].get("work", "")
            best = (distance, author, work, docs[0])

    if best is not None and best[0] <= MAX_DISTANCE:
        _, author, work, document = best
        bio = AUTHOR_BIOS.get(author, "")
        print(f"\n{author} felt something like this too:")
        print(f"  ({author} was {bio})")
        print(f"  {work}: {document}")
    else:
        print("\nNone of the philosophers seem to speak to this today.")

    # Before saving, look for a similar past journal entry (search by the
    # feelings sentence). Done before the save so the new entry can't match
    # itself.
    past = journal.query(
        query_texts=[feelings],
        n_results=1,
        where={"type": "journal"},
    )
    past_docs = past["documents"][0]
    if past_docs and past["distances"][0][0] < JOURNAL_DISTANCE:
        past_date = past["metadatas"][0][0].get("date", "an earlier day")
        print(f"\nYou wrote something similar on {past_date}: {past_docs[0]}")

    # Save the entry with its feelings sentence in the journal collection.
    add_journal_entry(journal, entry, feelings=feelings)
    print("\nSaved to your journal.")


# --------------------------------------------------------------------------- #
# ask one philosopher
# --------------------------------------------------------------------------- #
# Menu display names mapped to the author value stored in the collection.
PHILOSOPHERS = [
    ("Marcus Aurelius", "Marcus Aurelius"),
    ("Seneca", "Seneca"),
    ("Montaigne", "Michel de Montaigne"),
]


def ask_one_philosopher(collection):
    """Prompt for a philosopher and a feeling, then show that one's passages."""
    print("\nWhich philosopher?")
    for i, (display, _) in enumerate(PHILOSOPHERS, start=1):
        print(f"  {i}. {display}")
    choice = input("Choose a number: ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(PHILOSOPHERS)):
        print("That's not one of the choices.")
        return
    _, author = PHILOSOPHERS[int(choice) - 1]

    feeling = input("How do you feel? ").strip()
    if not feeling:
        print("Nothing entered, returning to the menu.")
        return

    if not _print_author_match(collection, author, feeling, n_results=2):
        print(f"\n{author} doesn't have much to say about this.")


# --------------------------------------------------------------------------- #
# view journal
# --------------------------------------------------------------------------- #
def view_journal(journal):
    """Print all journal entries with their dates, oldest first."""
    entries = journal.get(where={"type": "journal"})
    docs = entries["documents"]
    if not docs:
        print("\nYour journal is empty.")
        return

    # oldest first; id carries a nanosecond timestamp as a tiebreaker on date.
    rows = sorted(
        zip(entries["ids"], entries["metadatas"], docs),
        key=lambda r: (r[1].get("date", ""), r[0]),
    )
    print(f"\nYour journal ({len(rows)} entries):\n")
    for _id, meta, document in rows:
        print(f"[{meta.get('date', 'unknown date')}] {document}")
        feelings = meta.get("feelings")
        if feelings and feelings != document:
            print(f"    feelings: {feelings}")
        print()


# --------------------------------------------------------------------------- #
# menu
# --------------------------------------------------------------------------- #
MENU = """
What would you like to do?
  1. Write a journal entry
  2. Ask one philosopher
  3. View my journal
  4. Quit
"""


def main():
    collection = get_collection()
    journal = get_journal_collection()
    print(f"Philosophy collection holds {collection.count()} passages; "
          f"your journal holds {journal.count()} entries.")

    while True:
        print(MENU)
        choice = input("Choose a number: ").strip()

        if choice == "1":
            entry = input("Write your journal entry: ").strip()
            if not entry:
                print("Nothing entered, returning to the menu.")
                continue
            reflect_on_entry(collection, journal, entry)
        elif choice == "2":
            ask_one_philosopher(collection)
        elif choice == "3":
            view_journal(journal)
        elif choice == "4":
            print("Take care.")
            break
        else:
            print("Please choose a number from 1 to 4.")


if __name__ == "__main__":
    main()
