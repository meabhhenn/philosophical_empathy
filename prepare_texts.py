"""prepare_texts.py — clean the raw Gutenberg texts into texts_clean/.

Graders download the ORIGINAL files into texts/. This script reads those
originals and writes cleaned copies into texts_clean/, leaving texts/
untouched. readBook.py then loads from texts_clean/.

Each cleaner works on text with newlines normalised to "\n"; the original
CRLF line endings are restored on write.

Cleanups:
  Meditations  - keep only "THE FIRST BOOK" .. up to (not incl.) "APPENDIX".
  Montaigne    - keep only Book 1 ("CHAPTER I" .. "BOOK THE SECOND"); drop
                 ETEXT EDITOR bookmark blocks, title pages, "CONTENTS OF
                 VOLUME" lists, and inline --[ ... ]-- notes (-> single space).
  Seneca       - start at "THE FIRST BOOK OF THE DIALOGUES"; drop footnote
                 paragraphs starting with "[1]" etc.; strip inline "[4]"
                 markers and "{23}" page numbers.
"""

import os
import re

SRC_DIR = "texts"
OUT_DIR = "texts_clean"


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def read_original(name):
    """Read a source file; return (text_with_\n_newlines, original_newline)."""
    path = os.path.join(SRC_DIR, name)
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n").replace("\r", "\n"), newline


def write_clean(name, text, newline):
    """Write cleaned text to texts_clean/, restoring the original newline."""
    os.makedirs(OUT_DIR, exist_ok=True)
    out = text.strip() + "\n"
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8", newline="") as f:
        f.write(out.replace("\n", newline))
    return out


def tidy_blank_lines(text):
    """Collapse runs of 3+ blank lines into a single blank line."""
    return re.sub(r"\n{3,}", "\n\n", text)


# --------------------------------------------------------------------------- #
# Meditations
# --------------------------------------------------------------------------- #
def clean_meditations(text):
    """Keep "THE FIRST BOOK" up to (not including) the "APPENDIX" section.

    "APPENDIX" also appears earlier in the table of contents, so we only
    search for it after the real start marker.
    """
    start = text.find("THE FIRST BOOK")
    if start == -1:
        raise ValueError("meditations: 'THE FIRST BOOK' not found")

    end = text.find("APPENDIX", start)
    if end == -1:
        raise ValueError("meditations: 'APPENDIX' not found after start")

    return tidy_blank_lines(text[start:end]).strip()


# --------------------------------------------------------------------------- #
# Montaigne, Book 1
# --------------------------------------------------------------------------- #
_TITLE_LINE = "ESSAYS OF MICHEL DE MONTAIGNE"
_TITLE_FOLLOWERS = {
    "Translated by Charles Cotton",
    "Edited by William Carew Hazlitt",
    "BOOK THE FIRST",
}
_ROMAN_ENTRY = re.compile(r"^[IVXLCDM]+\.\s")  # TOC line e.g. "XIII.  ..."


def _is_toc_entry(s):
    return bool(_ROMAN_ENTRY.match(s)) or s.startswith(" ")  # entry or wrap


def clean_montaigne(text):
    """Keep Book 1 and strip bookmark blocks, title pages, TOC lists, notes."""
    lines = text.split("\n")
    try:
        start_i = next(i for i, l in enumerate(lines) if l == "CHAPTER I")
        end_i = next(i for i, l in enumerate(lines) if l == "BOOK THE SECOND")
    except StopIteration:
        raise ValueError("montaigne: could not locate Book 1 boundaries")
    block = lines[start_i:end_i]

    out = []
    i, n = 0, len(block)
    while i < n:
        line = block[i]

        # 1) ETEXT EDITOR'S BOOKMARKS heading + its indented/blank list lines
        if "ETEXT EDITOR" in line and "BOOKMARKS" in line:
            i += 1
            while i < n and (block[i].strip() == "" or block[i].startswith(" ")):
                i += 1
            continue

        # 2) Title page: ESSAYS... + blanks / attribution / 4-digit year
        if line.strip() == _TITLE_LINE:
            i += 1
            while i < n:
                s = block[i].strip()
                if s == "" or s in _TITLE_FOLLOWERS or re.fullmatch(r"\d{4}", s):
                    i += 1
                    continue
                break
            continue

        # 3) CONTENTS OF VOLUME list: header + roman-numeral entries/wraps
        if line.startswith("CONTENTS OF VOLUME"):
            i += 1
            while i < n:
                s = block[i]
                if s.strip() == "":
                    # swallow a blank only if more TOC entries still follow
                    j = i + 1
                    while j < n and block[j].strip() == "":
                        j += 1
                    if j < n and _is_toc_entry(block[j]):
                        i = j
                        continue
                    break
                if _is_toc_entry(s):
                    i += 1
                    continue
                break
            continue

        out.append(line)
        i += 1

    cleaned = "\n".join(out)

    # 4) inline notes --[ ... ]-- (may span lines, contain { } [ ] inside);
    #    replace with a single space so neighbouring words don't fuse.
    cleaned = re.sub(r"--\[.*?\]--", " ", cleaned, flags=re.DOTALL)
    # normalise any double spaces introduced on a single line (not newlines)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    return tidy_blank_lines(cleaned).strip()


# --------------------------------------------------------------------------- #
# Seneca, Minor Dialogues
# --------------------------------------------------------------------------- #
def clean_seneca(text):
    """Start at the first dialogues book; drop [N] footnote paragraphs;
    strip inline [N] markers and {N} page numbers."""
    start = text.find("THE FIRST BOOK OF THE DIALOGUES")
    if start == -1:
        raise ValueError("seneca: dialogues start marker not found")
    # back up to the beginning of that line
    line_start = text.rfind("\n", 0, start) + 1

    # stop before "THE END." (searched after the start) — everything past it
    # is the index, not dialogue text.
    end = text.find("THE END.", line_start)
    if end == -1:
        raise ValueError("seneca: 'THE END.' marker not found")
    body = text[line_start:end]

    # drop whole paragraphs that begin with a footnote marker like [1], [23]
    paragraphs = body.split("\n\n")
    kept = [p for p in paragraphs if not re.match(r"^\s*\[\d+\]", p)]
    body = "\n\n".join(kept)

    # strip remaining inline [N] citation markers and {N} page numbers
    body = re.sub(r"\[\d+\]", "", body)
    body = re.sub(r"\{\d+\}", "", body)

    # tidy spaces left where markers were removed
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r" +\n", "\n", body)

    return tidy_blank_lines(body).strip()


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
JOBS = [
    ("meditations.txt", clean_meditations),
    ("essays.txt", clean_montaigne),
    ("minor_dialogues.txt", clean_seneca),
]


def main():
    for name, cleaner in JOBS:
        text, newline = read_original(name)
        cleaned = cleaner(text)
        written = write_clean(name, cleaned, newline)
        print(f"{name}: {len(written.splitlines())} lines "
              f"({len(written)} chars) -> {OUT_DIR}/{name}")


if __name__ == "__main__":
    main()
