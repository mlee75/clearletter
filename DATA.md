# Data sources and licences

**Rule: no real patient data, ever.** Every letter in this repository is either a public,
de-identified sample or a synthetic letter written for this project.

## 1. MTSamples (20 documents)

- **What:** transcribed medical report samples (clinic letters, discharge summaries) from
  MTSamples.com. The site states: "All names and dates have been changed (or removed) to
  keep confidentiality."
- **Original source:** MTSamples, https://www.mtsamples.com (MTHelpLine).
- **Copy used:** the scrape by Tara Boyle published on Kaggle as
  [Medical Transcriptions](https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions)
  (4,999 rows), downloaded from the public mirror
  [harishnair04/mtsamples](https://huggingface.co/datasets/harishnair04/mtsamples) on
  Hugging Face (30 September 2026).
- **Licence, read carefully:**
  - The Kaggle upload is labelled **CC0: Public Domain**.
  - That label was added by the person who scraped the site, not by MTSamples. The
    original site's own terms say: "You may print, share, or link to these sample reports
    for educational purposes. When sharing or linking, please give credit to our site with
    a link to https://www.mtsamples.com".
  - This project follows the stricter of the two: **educational, non-commercial use,
    with credit to MTSamples.com**. It includes only the 20 documents it needs, not the
    full dataset.
- **What was changed:** the scrape replaced line breaks with commas. `tools/prepare_mtsamples.py`
  puts the line breaks back (`":,"` and `".,"`). No wording is changed.
- **Reproduce:** download `mtsamples.csv` into `data/raw/` (git-ignored), then run
  `python tools/prepare_mtsamples.py`.
- **Caveats:** these are US documents written for other doctors, not for patients. The
  site says the samples are "not guaranteed to be complete or error free". That makes them
  a realistic, hard test, not a clean one.

**Citation:** MTSamples. *Transcribed Medical Transcription Sample Reports and Examples.*
https://www.mtsamples.com. Accessed via Boyle, T. *Medical Transcriptions* (Kaggle).

## 2. Synthetic letters (20 documents)

- **What:** 20 short UK-style letters in `data/synthetic/` (5 appointment, 5 discharge,
  5 test results, 5 medication change), each built around a known trap: abbreviations,
  negations, dose changes, tapering schedules, UK day/month dates, deadlines, old vs new
  appointment dates. The trap for each letter is listed in `data/manifest.csv`.
- **Who wrote them:** drafted with Claude for this project and checked by the author.
  All weekday/date pairs were checked with a script.
- **Everything is fictional:** patients, clinicians, hospitals and practices. Phone numbers
  use the 01632 960xxx range, which Ofcom reserves for fiction. The only real numbers are
  public services (NHS 111, 999, Samaritans 116 123).
- **Not clinical guidance.** Doses are realistic so the test is realistic, but these letters
  must not be used as medical advice.
- **Licence:** MIT, like the rest of this repository.

## 3. Gold facts

`gold/facts/*.json` hold the "must-keep facts" for each letter (406 facts across 40 letters),
released under the MIT licence.

**Provenance, stated plainly:** all 40 files were drafted by Claude (Opus 5.5), at the
author's request, by reading each letter; no API was called. Each file says
`"reviewer": "claude-draft"` until the author reviews it with `python review.py <letter_id>`,
which records their initials instead. Because a Claude model wrote the answer key for a
Claude model, results measured against unreviewed drafts should be read with that in mind.
A script confirmed that every number in every fact appears in its letter.
