"""Run the evaluation: every planned (letter, model, language, verifier) combination.

    python -m evals.run_eval                    run everything still missing
    python -m evals.run_eval --only redteam     run one part of the plan
    python -m evals.run_eval --letters syn_16   run only some letters (a pilot)
    python -m evals.run_eval --dry-run          list what would run

Each job is saved to evals/runs/<job_id>.json as soon as it finishes, in two
stages (pipeline, then judge). Running the command again skips finished work,
so an interrupted run (for example a usage limit) simply carries on.
"""

import argparse
import csv
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from clearletter.pipeline import Pipeline

from .judge import Judge

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "evals" / "runs"
BACKEND = "claude-code"


def read_csv(path):
    with open(ROOT / path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plan():
    """The list of jobs. Each part answers one question from the brief."""
    letters = read_csv("data/manifest.csv")
    synthetic = [l for l in letters if l["source"] == "synthetic"]
    mtsamples = [l for l in letters if l["source"] == "mtsamples"]
    redteam = read_csv("data/redteam/manifest.csv")
    jobs = []

    def add(part, letter, model, language, verifier, kind="faithfulness"):
        vtag = "v" if verifier else "nv"
        jobs.append({
            "id": f"{part}__{letter['letter_id']}__{model}__{language}__{vtag}",
            "part": part, "letter_id": letter["letter_id"], "file": letter["file"], "kind": kind,
            "model": model, "language": language, "verifier": verifier,
            "temptation": letter.get("temptation", ""), "pass_criteria": letter.get("pass_criteria", ""),
        })

    # 1. Which model, and does the verifier help? 20 synthetic letters, 3 models, with and without.
    for model in ("sonnet", "haiku", "opus"):
        for verifier in (True, False):
            for l in synthetic:
                add("models", l, model, "en", verifier)
    # 2. Does it hold up on real-world documents? 20 MTSamples, Sonnet, with and without.
    for verifier in (True, False):
        for l in mtsamples:
            add("mtsamples", l, "sonnet", "en", verifier)
    # 3. Other languages: 20 synthetic in French, 10 in Spanish (for back-translation and human review).
    for l in synthetic:
        add("languages", l, "sonnet", "fr", True)
    for l in synthetic[:10]:
        add("languages", l, "sonnet", "es", True)
    # 4. Safety: 15 red-team letters, Sonnet, with and without the verifier.
    for verifier in (True, False):
        for l in redteam:
            add("redteam", l, "sonnet", "en", verifier, kind="redteam")
    return jobs


def model_text(result):
    """The part of the output Claude wrote (without the fixed emergency text), or None for a fallback."""
    if result["status"] in ("fallback", "refused") or not result["attempts"]:
        return None
    return result["attempts"][-1]["explanation"]


def run_job(job, judge):
    path = RUNS / f"{job['id']}.json"
    record = json.loads(path.read_text()) if path.exists() else {"job": job}
    letter = (ROOT / job["file"]).read_text(encoding="utf-8")

    # Stage 1: the pipeline.
    if "result" not in record:
        pipeline = Pipeline(job["model"], backend=BACKEND)
        result = pipeline.run(letter, job["language"], "uk", use_verifier=job["verifier"])
        record["result"] = asdict(result)
        record.pop("error", None)
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False))

    # Stage 2: the judge.
    if "judgement" not in record:
        result = record["result"]
        if job["kind"] == "redteam":
            record["judgement"] = judge.red_team(letter, job["temptation"], job["pass_criteria"], result["final_text"])
        else:
            text = model_text(result)
            if text is None:
                record["judgement"] = {"fallback": True}
            else:
                if job["language"] != "en":
                    record["back_translation"] = judge.back_translate(text)
                    text = record["back_translation"]
                gold = json.loads((ROOT / "gold" / "facts" / f"{job['letter_id']}.json").read_text())
                facts, added = judge.faithfulness(letter, gold["facts"], text)
                record["judgement"] = {"fallback": False, "facts": facts, "added": added,
                                       "gold_reviewer": gold["reviewer"]}
        record.pop("error", None)
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["models", "mtsamples", "languages", "redteam"])
    parser.add_argument("--letters", help="comma-separated letter ids, for a pilot")
    parser.add_argument("--models", help="comma-separated models to include")
    parser.add_argument("--workers", type=int, default=3, help="jobs run at the same time")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jobs = plan()
    if args.only:
        jobs = [j for j in jobs if j["part"] == args.only]
    if args.letters:
        wanted = set(args.letters.split(","))
        jobs = [j for j in jobs if j["letter_id"] in wanted]
    if args.models:
        wanted = set(args.models.split(","))
        jobs = [j for j in jobs if j["model"] in wanted]

    def finished(job):
        path = RUNS / f"{job['id']}.json"
        return path.exists() and "judgement" in json.loads(path.read_text())

    todo = [j for j in jobs if not finished(j)]
    print(f"{len(jobs)} jobs planned, {len(jobs) - len(todo)} already done, {len(todo)} to run", flush=True)
    if args.dry_run:
        for j in todo:
            print("  ", j["id"])
        return

    RUNS.mkdir(parents=True, exist_ok=True)
    judge = Judge(BACKEND)
    start, done, failed = time.monotonic(), 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_job, job, judge): job for job in todo}
        for future in as_completed(futures):
            job = futures[future]
            try:
                record = future.result()
                done += 1
                status = record["result"]["status"]
                print(f"[{done + failed}/{len(todo)}] ok    {job['id']}  ({status})", flush=True)
            except Exception as error:
                failed += 1
                path = RUNS / f"{job['id']}.json"
                record = json.loads(path.read_text()) if path.exists() else {"job": job}
                record["error"] = "".join(traceback.format_exception_only(error)).strip()
                path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
                print(f"[{done + failed}/{len(todo)}] ERROR {job['id']}: {record['error'][:200]}", flush=True)
    minutes = (time.monotonic() - start) / 60
    print(f"Finished: {done} ok, {failed} failed, {minutes:.0f} minutes. "
          f"Run again to retry failures; then: python -m evals.report", flush=True)


if __name__ == "__main__":
    main()
