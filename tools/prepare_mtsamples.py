"""Pick 20 public MTSamples reports and save each one as a plain text file.

Why this script exists: anyone can re-run it and get exactly the same 20
letters, so the data choice is transparent and repeatable.

Input:  data/raw/mtsamples.csv   (downloaded once, not committed; see DATA.md)
Output: data/mtsamples/mts_<id>.txt

Run:    python tools/prepare_mtsamples.py
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "mtsamples.csv"
OUT_DIR = ROOT / "data" / "mtsamples"

# Chosen by hand: short documents (under ~2,600 characters) that a patient
# could realistically receive a copy of. 10 clinic letters + 10 discharge
# summaries, across different specialties. The number is the row id in the CSV.
CHOSEN_IDS = [
    # Letters
    "3057", "3058", "3060", "3061", "3066", "3068", "3069", "3072", "3073", "3080",
    # Discharge summaries
    "3889", "3898", "3899", "3909", "3912", "3918", "3922", "3974", "3977", "3980",
]


def clean(text):
    """The scraped CSV lost its line breaks and put commas in their place
    (for example "HOSPITAL COURSE:,The patient..."). Put the line breaks back.
    Nothing else in the wording is changed."""
    text = text.strip()
    text = text.replace(":,", ":\n")
    text = text.replace(".,", ".\n")
    return text


def main():
    rows = {row[""]: row for row in csv.DictReader(RAW_CSV.open(encoding="utf-8"))}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for row_id in CHOSEN_IDS:
        row = rows[row_id]
        path = OUT_DIR / f"mts_{row_id}.txt"
        path.write_text(clean(row["transcription"]) + "\n", encoding="utf-8")
        print(f"{path.name:14} {row['medical_specialty'].strip():20} {row['sample_name'].strip()}")


if __name__ == "__main__":
    main()
