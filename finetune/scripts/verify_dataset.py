"""Check every citation in the dataset against the real PDF page it names.

This is the guard that makes the dataset trustworthy. A fine-tuned model copies the
habits in its training data: if the data cites the wrong page, the model learns to cite
confidently and wrongly, which is worse than not citing at all.

Two checks, and the second one is the interesting one:

  1. Does the answer's vocabulary actually appear on the page it cites?
  2. Is that page a table of contents? A contents line like "Severability ......"
     matches the topic words perfectly while containing none of the rule. Both broken
     citations in the original data were exactly this.

Word overlap is a screening tool, not a verdict. Anything it flags is printed for a
human to read - it is not silently "corrected".

Run:  python scripts/verify_dataset.py            (checks train.jsonl and eval.jsonl)
Exit: 0 all clear · 1 something needs a human
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "docs"

CITATION = re.compile(r"\(([\w_]+\.pdf),\s*p\.?\s*(\d+)\)")
WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
CONFIDENT = 0.60          # overlap at or above this needs no human
SUSPICIOUS = 0.40         # below this is almost certainly wrong

REFUSAL = (
    "I can only answer questions about these loan/credit terms and conditions. "
    "I can't help with that."
)
NOT_STATED = "Not stated in the terms."

# Rows a human opened the PDF for and confirmed, keyed by a distinctive phrase from the
# question. Recording the judgement is the honest fix; lowering the threshold instead
# would silence real problems along with this one.
#
# Word overlap cannot separate a clause from a passing mention. Page 10 of the CIBC
# document uses the word "dispute" inside a governing-law sentence, so it scores well on
# vocabulary. Page 12 carries the actual definition and its exclusions:
#   "A dispute does not include any claim or action by CIBC to obtain payment from you…"
# That is the clause the answer quotes, so page 12 is right and the score is misleading.
VERIFIED_BY_HAND: dict[str, str] = {
    "excluded from the definition of a dispute": (
        "p.12 holds the definition and its exclusions; p.10 only mentions the word in a "
        "governing-law sentence"
    ),
}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(dict.fromkeys(map(ord, "‘’ʻʼʽ′`'´"), None))
    return re.sub(r"\s+", " ", text.lower())


_pages: dict[str, list[str]] = {}


def pages(name: str) -> list[str] | None:
    if name not in _pages:
        path = DOCS / name
        if not path.exists():
            return None
        _pages[name] = [normalise(p.extract_text() or "") for p in PdfReader(str(path)).pages]
    return _pages[name]


def is_contents_page(page: str) -> bool:
    return len(re.findall(r"\.{4,}", page)) >= 5


def overlap(answer_body: str, page: str) -> float:
    words = {normalise(w) for w in WORD.findall(answer_body)}
    if not words:
        return 0.0
    return sum(1 for w in words if w in page) / len(words)


def check(path: Path) -> tuple[int, int, list[str]]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    problems: list[str] = []
    kinds: Counter[str] = Counter()
    verified = 0

    for index, r in enumerate(rows):
        msgs = r.get("messages", [])
        if [m["role"] for m in msgs] != ["system", "user", "assistant"]:
            problems.append(f"[{index}] wrong message roles: {[m['role'] for m in msgs]}")
            continue

        answer = msgs[2]["content"].strip()

        if answer == NOT_STATED:
            kinds["not_stated"] += 1
            continue
        if answer == REFUSAL:
            kinds["refusal"] += 1
            continue
        kinds["answered"] += 1

        match = CITATION.search(answer)
        if not match:
            problems.append(f"[{index}] an answered row with no citation: {answer[:70]}…")
            continue

        name, page_no = match.group(1), int(match.group(2))
        doc = pages(name)
        if doc is None:
            problems.append(f"[{index}] cites a document that is not in data/docs: {name}")
            continue
        if not 1 <= page_no <= len(doc):
            problems.append(f"[{index}] {name} has {len(doc)} pages but the row cites p.{page_no}")
            continue

        page = doc[page_no - 1]
        body = CITATION.sub("", answer).strip()

        if is_contents_page(page):
            best = max(range(1, len(doc) + 1), key=lambda p: overlap(body, doc[p - 1]))
            problems.append(
                f"[{index}] {name} p.{page_no} is a contents page, not a clause "
                f"(the rule is probably on p.{best})"
            )
            continue

        score = overlap(body, page)
        by_hand = next(
            (note for phrase, note in VERIFIED_BY_HAND.items() if phrase in msgs[1]["content"]),
            None,
        )
        if score >= CONFIDENT or by_hand:
            verified += 1
            if by_hand and score < CONFIDENT:
                print(f"  [{index}] {score:.0%} overlap, confirmed by hand: {by_hand}")
        else:
            best_page = max(range(1, len(doc) + 1), key=lambda p: overlap(body, doc[p - 1]))
            best_score = overlap(body, doc[best_page - 1])
            severity = "LIKELY WRONG" if score < SUSPICIOUS else "worth a look"
            note = f" (p.{best_page} scores {best_score:.0%})" if best_page != page_no else " (still the best page)"
            problems.append(
                f"[{index}] {severity}: {name} p.{page_no} matches {score:.0%}{note}\n"
                f"        Q: {msgs[1]['content'][:80]}"
            )

    print(f"\n{path.name}: {len(rows)} rows   " + "  ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print(f"  citations verified against the page: {verified}/{kinds['answered']}")
    if kinds["refusal"] == 0 or kinds["not_stated"] == 0:
        problems.append(
            "this file cannot measure refusal or not-stated behaviour - it has none of them"
        )
    return verified, kinds["answered"], problems


def main() -> int:
    all_problems: list[tuple[str, list[str]]] = []
    for name in ("train.jsonl", "eval.jsonl"):
        path = ROOT / "data" / name
        if not path.exists():
            print(f"{name} is missing - run scripts/build_dataset.py first")
            return 1
        _, _, problems = check(path)
        if problems:
            all_problems.append((name, problems))

    if not all_problems:
        print("\nEvery citation points at a page that really contains the clause. ✅")
        return 0

    print("\nNeeds a human:")
    for name, problems in all_problems:
        print(f"\n  {name}")
        for p in problems:
            print(f"    {p}")
    print(
        "\nNothing here has been auto-corrected. Open the PDF at the page named, read the\n"
        "clause, and fix the row by hand - a citation is only worth anything if it is true."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
