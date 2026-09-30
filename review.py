"""Review tool: write the "must-keep facts" for each letter, by hand.

These facts are the gold standard for the whole project. In Phase 3 the eval
checks whether Claude's explanation kept every one of them. A human writes
them (not Claude), so the test is not marking its own homework.

Usage:
    python review.py            review the next letter that has no facts yet
    python review.py status     show which letters are done
    python review.py syn_07     review (or redo) one specific letter

Facts are saved as one small JSON file per letter in gold/facts/.
Uses only the Python standard library: nothing to install.
"""

import csv
import hashlib
import json
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "data" / "manifest.csv"
GOLD_DIR = ROOT / "gold" / "facts"

# The kinds of fact we ask for, in order, with a hint shown while typing.
CATEGORIES = [
    ("diagnoses", "Conditions or findings the letter states (keep 'possible' / 'suspected' words)."),
    ("medicines", "One per medicine: name + dose + how often + what changed (start/stop/continue/increase/decrease)."),
    ("dates", "Appointments, tests, deadlines, durations: what + when (copy numbers exactly)."),
    ("actions", "What the patient (or carer) must do or must not do."),
    ("negatives", "Important 'no' / 'not' findings the explanation must not flip (e.g. 'no fracture')."),
]


def load_letters():
    """Read the list of letters from data/manifest.csv."""
    with MANIFEST.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fact_path(letter_id):
    return GOLD_DIR / f"{letter_id}.json"


def show_letter(letter):
    """Print the letter with line numbers so it is easy to refer back to."""
    text = (ROOT / letter["file"]).read_text(encoding="utf-8")
    print("\n" + "=" * 78)
    print(f"LETTER {letter['letter_id']}   ({letter['source']}, {letter['letter_type']})")
    print("=" * 78)
    number = 1
    for line in text.splitlines():
        for part in textwrap.wrap(line, 72) or [""]:
            print(f"{number:3} | {part}")
            number += 1
    print("=" * 78)
    return text


def ask_category(name, hint, letter):
    """Collect facts for one category until the reviewer presses Enter on an empty line."""
    print(f"\n--- {name.upper()} ---  {hint}")
    print("    Enter = next category   'undo' = remove last   '?' = show letter again   'q' = quit")
    facts = []
    while True:
        answer = input("  + ").strip()
        if answer == "":
            return facts
        if answer == "q":
            raise KeyboardInterrupt
        if answer == "?":
            show_letter(letter)
        elif answer == "undo":
            if facts:
                print(f"    removed: {facts.pop()}")
        else:
            facts.append(answer)


def review(letter, reviewer):
    """Show one letter, collect its facts, and save them if the reviewer confirms."""
    existing = fact_path(letter["letter_id"])
    if existing.exists():
        print(f"\nThis letter already has facts. Here they are; you are about to replace them:")
        print(existing.read_text(encoding="utf-8"))

    text = show_letter(letter)
    facts = {name: ask_category(name, hint, letter) for name, hint in CATEGORIES}
    notes = input("\nAny notes (ambiguities, things you were unsure about)? ").strip()

    print("\nSUMMARY")
    for name, items in facts.items():
        print(f"  {name}: {len(items)}")
        for item in items:
            print(f"     - {item}")

    choice = input("\nSave? [y]es / [r]edo this letter / [n]o, skip it: ").strip().lower()
    if choice == "r":
        return review(letter, reviewer)
    if choice != "y":
        print("Not saved.")
        return

    record = {
        "letter_id": letter["letter_id"],
        "reviewer": reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # A fingerprint of the letter text. If someone edits the letter later,
        # the eval can notice that these facts were written for an older version.
        "letter_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "facts": facts,
        "notes": notes,
    }
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    existing.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved to {existing.relative_to(ROOT)}")


def status(letters):
    done = [l for l in letters if fact_path(l["letter_id"]).exists()]
    print(f"\n{len(done)} of {len(letters)} letters reviewed\n")
    for l in letters:
        mark = "done" if fact_path(l["letter_id"]).exists() else "  - "
        print(f"  [{mark}] {l['letter_id']:9} {l['letter_type']:18} {l['tricky_features'][:45]}")


def main():
    letters = load_letters()
    args = sys.argv[1:]

    if args and args[0] == "status":
        status(letters)
        return

    if args:
        chosen = [l for l in letters if l["letter_id"] == args[0]]
        if not chosen:
            print(f"No letter called {args[0]!r}. Run 'python review.py status' to see the ids.")
            return
    else:
        chosen = [l for l in letters if not fact_path(l["letter_id"]).exists()]
        if not chosen:
            print("All letters are reviewed. Well done.")
            return

    reviewer = input("Your initials: ").strip() or "unknown"
    try:
        for letter in chosen:
            review(letter, reviewer)
            if args or input("\nNext letter? [Enter] = yes, 'q' = stop: ").strip() == "q":
                break
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. The letter you were on was not saved.")
    status(letters)


if __name__ == "__main__":
    main()
