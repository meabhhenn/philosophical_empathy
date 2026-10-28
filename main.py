"""main.py — open the philosophy collection and work with journal entries.

The collection is built by readBook.py (the philosophical texts). This module
adds personal journal entries alongside those book chunks, tagged so they can
be queried on their own via where={"type": "journal"}.
"""

import datetime
import time

import chromadb


def get_collection():
    """Open the same persistent collection that readBook.py populates."""
    client = chromadb.PersistentClient(path="chroma_db")
    return client.get_or_create_collection(name="philosophy")


def add_journal_entry(collection, text):
    """Save a journal entry to the collection.

    Metadata is type="journal" plus today's date (YYYY-MM-DD). The id is based
    on the current timestamp so each entry is unique.

    Returns the id that was used.
    """
    entry_id = f"journal-{time.time_ns()}"  # nanosecond timestamp -> unique id
    today = datetime.date.today().isoformat()
    collection.add(
        documents=[text],
        ids=[entry_id],
        metadatas=[{"type": "journal", "date": today}],
    )
    return entry_id


AUTHORS = ["Marcus Aurelius", "Seneca", "Michel de Montaigne"]

# Distance thresholds (smaller distance = closer match).
MAX_DISTANCE = 1.55    # above this, treat as "nothing to say"
STRONG_DISTANCE = 1.45  # below this, label a match as "strong"
JOURNAL_DISTANCE = 1.3  # stricter cutoff for the past-journal echo


def reflect(collection, feeling):
    """Find philosophical passages (and a past journal echo) for a feeling.

    Searches the books one author at a time and the journal separately, prints
    the relevant matches, then saves the feeling as a new journal entry (last,
    so it can't match itself).
    """
    # (1) one query per author, keep the single closest passage each.
    matches = []
    for author in AUTHORS:
        res = collection.query(
            query_texts=[feeling],
            n_results=1,
            where={"author": author},
        )
        docs = res["documents"][0]
        if not docs:
            print(f"{author} doesn't have much to say about this")
            continue
        distance = res["distances"][0][0]
        meta = res["metadatas"][0][0]
        document = docs[0]

        # (2) drop anything too far away.
        if distance > MAX_DISTANCE:
            print(f"{author} doesn't have much to say about this")
            continue
        matches.append((distance, author, meta.get("work", ""), document))

    # (3) print surviving passages, closest first, with a match-strength label.
    if matches:
        matches.sort(key=lambda m: m[0])
        print()
        for distance, author, work, document in matches:
            label = "strong match" if distance < STRONG_DISTANCE else "loose match"
            print(f"{author}, {work} ({label}):")
            print(f"  {document}\n")
    else:
        # (4) nothing cleared the threshold for any author.
        print(
            "\nNone of the philosophers seem to speak to this. "
            "Try describing the feeling differently."
        )

    # (5) look for a similar past journal entry.
    print_journal_echo(collection, feeling)

    # (6) finally, save this feeling as a new journal entry (after searching,
    #     so it never matches itself above).
    add_journal_entry(collection, feeling)


def print_journal_echo(collection, feeling):
    """Print the closest past journal entry if it's within the cutoff."""
    journal = collection.query(
        query_texts=[feeling],
        n_results=1,
        where={"type": "journal"},
    )
    journal_docs = journal["documents"][0]
    if journal_docs and journal["distances"][0][0] < JOURNAL_DISTANCE:
        distance = journal["distances"][0][0]
        past_date = journal["metadatas"][0][0].get("date", "an earlier day")
        # distance printed for tuning; remove once the cutoff feels right
        print(f"You felt something similar on {past_date} "
              f"(distance {distance:.3f}): {journal_docs[0]}")


def reflect_one(collection, author, feeling):
    """Show one philosopher's best passages (top 2, same cutoff) for a feeling.

    Prints the journal echo and saves the feeling as a new entry, like reflect.
    """
    res = collection.query(
        query_texts=[feeling],
        n_results=2,
        where={"author": author},
    )
    docs = res["documents"][0]

    # keep only the passages within the cutoff, closest first (query is already
    # ordered by distance, but filter against MAX_DISTANCE).
    matches = []
    for i, document in enumerate(docs):
        distance = res["distances"][0][i]
        if distance > MAX_DISTANCE:
            continue
        work = res["metadatas"][0][i].get("work", "")
        matches.append((distance, work, document))

    if matches:
        print()
        for distance, work, document in matches:
            label = "strong match" if distance < STRONG_DISTANCE else "loose match"
            print(f"{author}, {work} ({label}):")
            print(f"  {document}\n")
    else:
        print(f"\n{author} doesn't have much to say about this.")

    print_journal_echo(collection, feeling)
    add_journal_entry(collection, feeling)


def view_journal(collection):
    """Print all journal entries with their dates, oldest first."""
    entries = collection.get(where={"type": "journal"})
    docs = entries["documents"]
    metas = entries["metadatas"]
    if not docs:
        print("\nYour journal is empty.")
        return

    # sort oldest first. The id carries a nanosecond timestamp, so fall back to
    # it when two entries share a date.
    rows = sorted(
        zip(entries["ids"], metas, docs),
        key=lambda r: (r[1].get("date", ""), r[0]),
    )
    print(f"\nYour journal ({len(rows)} entries):\n")
    for _id, meta, document in rows:
        print(f"[{meta.get('date', 'unknown date')}] {document}\n")


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
    reflect_one(collection, author, feeling)


MENU = """
What would you like to do?
  1. Tell me how you feel
  2. Ask one philosopher
  3. Write a journal entry
  4. View my journal
  5. Quit
"""


def main():
    collection = get_collection()
    print(f"Philosophy collection holds {collection.count()} stored items.")

    while True:
        print(MENU)
        choice = input("Choose a number: ").strip()

        if choice == "1":
            feeling = input("How do you feel? ").strip()
            if not feeling:
                print("Nothing entered, returning to the menu.")
                continue
            reflect(collection, feeling)
        elif choice == "2":
            ask_one_philosopher(collection)
        elif choice == "3":
            text = input("Write your journal entry: ").strip()
            if not text:
                print("Nothing entered, returning to the menu.")
                continue
            add_journal_entry(collection, text)
            print("Saved.")
        elif choice == "4":
            view_journal(collection)
        elif choice == "5":
            print("Take care.")
            break
        else:
            print("Please choose a number from 1 to 5.")


if __name__ == "__main__":
    main()
