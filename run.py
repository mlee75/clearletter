"""Explain one letter from the command line.

Examples:
    python run.py data/synthetic/syn_16.txt
    python run.py data/synthetic/syn_16.txt --lang fr --country uk --model haiku
    python run.py data/synthetic/syn_16.txt --no-verifier

Every run is saved to outputs/ and its cost is added to outputs/spend_log.csv,
so the total API spend is always known.
"""

import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from clearletter.config import MODELS
from clearletter.fixed_text import COUNTRIES, LANGUAGES
from clearletter.pipeline import Pipeline

OUTPUTS = Path(__file__).resolve().parent / "outputs"


def log_spend(letter_path, result):
    OUTPUTS.mkdir(exist_ok=True)
    log = OUTPUTS / "spend_log.csv"
    is_new = not log.exists()
    with log.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["time", "letter", "model", "language", "verifier", "status", "cost_usd"])
        writer.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), letter_path,
                         result.model, result.language, result.use_verifier, result.status, result.cost_usd])
    with log.open() as f:
        return sum(float(row["cost_usd"]) for row in csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser(description="Explain a medical letter in plain language (prototype).")
    parser.add_argument("letter", help="path to a .txt letter")
    parser.add_argument("--lang", choices=LANGUAGES, default="en")
    parser.add_argument("--country", choices=COUNTRIES, default="uk")
    parser.add_argument("--model", choices=MODELS, default="sonnet")
    parser.add_argument("--no-verifier", action="store_true", help="skip step 3 (baseline for the eval)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("No API key found. Copy .env.example to .env and paste your key into it.")

    letter = Path(args.letter).read_text(encoding="utf-8")
    result = Pipeline(args.model).run(letter, args.lang, args.country, use_verifier=not args.no_verifier)

    print(result.final_text)
    print("=" * 70)
    print(f"Status: {result.status}   Model: {result.model}   "
          f"Cost: ${result.cost_usd:.4f}   Time: {result.latency_s}s")
    if result.removed_ungrounded:
        print(f"Grounding check removed {len(result.removed_ungrounded)} extracted item(s) not found in the letter.")
    for a in result.attempts:
        r = a["readability"]
        print(f"Attempt {a['attempt']}: {len(a['blocking_problems'])} blocking problem(s); "
              f"reading ease {r['reading_ease']}" + (f", grade {r['grade_level']}" if "grade_level" in r else ""))
        for p in a["blocking_problems"]:
            print(f"   - {p}")

    OUTPUTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUTPUTS / f"{Path(args.letter).stem}_{args.model}_{args.lang}_{stamp}.json"
    out.write_text(result.to_json(), encoding="utf-8")
    total = log_spend(args.letter, result)
    print(f"Saved: {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    print(f"Total API spend so far: ${total:.2f} of the $20 budget")


if __name__ == "__main__":
    main()
