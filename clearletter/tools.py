"""The two tools: an abbreviation glossary and a readability scorer.

Each tool is a normal Python function first (easy to test, no AI involved).
At the bottom, the same functions are wrapped with @beta_tool so Claude can
call them while it writes the explanation.
"""

import csv
import re
from pathlib import Path

import textstat
from anthropic import beta_tool

GLOSSARY_FILE = Path(__file__).resolve().parent.parent / "data" / "glossary.csv"

# Reading-level targets from SPEC.md section 4. Higher Reading Ease = easier.
READING_EASE_TARGET = 70
GRADE_TARGET_EN = 6


def load_glossary():
    with GLOSSARY_FILE.open(encoding="utf-8") as f:
        return {row["term"]: row["meaning"] for row in csv.DictReader(f)}


GLOSSARY = load_glossary()


def lookup_term(term):
    """Look up one abbreviation. Exact match first, then ignoring upper/lower case."""
    term = term.strip()
    if term in GLOSSARY:
        return f"{term}: {GLOSSARY[term]}"
    for known, meaning in GLOSSARY.items():
        if known.lower() == term.lower():
            return f"{known}: {meaning}"
    # Saying "not found" clearly stops the model from guessing a meaning.
    return (
        f"'{term}' is not in the glossary. Do not guess what it means. "
        "Keep the term as it is written in the letter and suggest the patient asks their doctor about it."
    )


def find_terms_in_letter(letter):
    """Find every glossary term that appears in the letter.

    This runs in plain code, before Claude sees the letter, so the extraction
    step always gets the right meanings: it cannot forget to look one up.
    Matching is case-sensitive ("ON" means "at night", "on" does not).
    """
    found = {}
    for term, meaning in GLOSSARY.items():
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        if re.search(pattern, letter):
            found[term] = meaning
    return found


def readability(text, language):
    """Score how easy a text is to read. Returns a dict of scores and a pass/fail."""
    # Remove markdown symbols (#, *, |) so they do not count as words.
    plain = re.sub(r"[#*|>`_]", " ", text)
    textstat.set_lang(language)
    # For "fr" textstat uses the Kandel & Moles constants, for "es" Fernandez-Huerta.
    reading_ease = round(textstat.flesch_reading_ease(plain), 1)
    scores = {"language": language, "reading_ease": reading_ease, "reading_ease_target": READING_EASE_TARGET}
    passed = reading_ease >= READING_EASE_TARGET
    if language == "en":
        grade = round(textstat.flesch_kincaid_grade(plain), 1)
        scores.update(grade_level=grade, grade_target=GRADE_TARGET_EN)
        passed = passed and grade <= GRADE_TARGET_EN
    scores["passed"] = passed
    return scores


# ---- The same functions, wrapped so Claude can call them as tools ----------

@beta_tool
def glossary_lookup(term: str) -> str:
    """Look up what a medical abbreviation means in plain English, using a fixed glossary.
    If the term is not in the glossary, do not guess its meaning.

    Args:
        term: The abbreviation exactly as written in the letter, for example "TDS" or "CXR".
    """
    return lookup_term(term)


@beta_tool
def readability_check(text: str, language: str) -> str:
    """Score how easy a draft is to read. Target: Reading Ease 70 or more, and for English
    a Flesch-Kincaid grade of 6 or less. If it fails, use shorter sentences and simpler words.

    Args:
        text: The draft explanation to score.
        language: "en", "fr" or "es".
    """
    if language not in ("en", "fr", "es"):
        return "Error: language must be 'en', 'fr' or 'es'."
    return str(readability(text, language))
