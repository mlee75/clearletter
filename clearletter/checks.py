"""Safety checks written in plain code (no AI).

They are cheap, fast and never "change their mind", so they catch a few
specific mistakes every time. The AI verifier (in pipeline.py) catches the
subtler ones, like a lost "not" or advice that sounds reasonable but is new.
"""

import re

from .fixed_text import HEADINGS

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}


def normalise(text):
    """Lower case, straight quotes, single spaces: so small formatting differences don't matter."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


def words(text):
    """Only the words and numbers, lower case: " word word word ". Punctuation, bullets
    and line breaks are ignored, so a quote that runs across two bullet points still matches."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", normalise(text))) + " "


def quote_is_in_letter(quote, letter):
    """True if every part of the quote appears, word for word, in the letter.
    A quote may skip text with "..."; each part must still be found."""
    parts = [part for part in re.split(r"\.\.\.|\u2026", quote) if words(part).strip()]
    return bool(parts) and all(words(part) in words(letter) for part in parts)


def remove_ungrounded(facts, letter):
    """Grounding check: drop any extracted item whose quote is not really in the letter.

    If the extractor invented something, its quote will not be found, so the
    invented item never reaches the explanation. Returns the removed items.
    """
    removed = []
    for list_name in ("findings", "medicines", "dates", "actions", "negatives", "warning_signs"):
        kept = []
        for item in getattr(facts, list_name):
            if quote_is_in_letter(item.quote, letter):
                kept.append(item)
            else:
                removed.append({"list": list_name, "item": item.model_dump()})
        setattr(facts, list_name, kept)
    return removed


def numbers_in(text):
    """All the numbers in a text, as strings without leading zeros.
    "03/12/2026" gives {"3", "12", "2026"}; "7,5 ml" and "7.5 ml" both give {"7", "5"}."""
    return {str(int(n)) for n in re.findall(r"\d+", text)}


def unknown_numbers(explanation, letter):
    """Numbers check: every number in the explanation must also be in the letter.

    This catches a changed dose, a wrong date, or a phone number the model made
    up. List markers like "1." at the start of a line are ignored.
    """
    without_list_markers = re.sub(r"(?m)^\s*\d+[.)]\s", " ", explanation)
    allowed = numbers_in(letter)
    for word, digit in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", letter, re.IGNORECASE):
            allowed.add(digit)
    return sorted(numbers_in(without_list_markers) - allowed, key=int)


def missing_headings(explanation, language):
    """Structure check: the five section headings must all be there."""
    return [h for h in HEADINGS[language] if h.lower() not in explanation.lower()]
