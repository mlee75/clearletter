"""The clearletter pipeline: extract -> explain -> verify.

    letter --(1) extract--> facts (JSON) --(2) explain--> draft --(3) verify--> output
                                                ^                     |
                                                +--- retry once ------+  (if problems)
                                                     then fallback: "ask your doctor"

Step 2 never sees the letter, only the facts. That is on purpose: the
explanation can only contain what step 1 found in the letter.
Step 3 does see the letter, so it can catch anything step 1 missed or got wrong.
"""

import json
import time
from dataclasses import asdict, dataclass, field

from . import checks, fixed_text, prompts
from .backends import make_backend
from .config import MODELS
from .schemas import ExtractedFacts, VerifierReport
from .tools import find_terms_in_letter, readability

LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish"}


class Refused(Exception):
    """Claude declined to answer (stop_reason "refusal"). We show the fallback."""


@dataclass
class Result:
    """Everything about one run: the output, and what was checked along the way."""
    model: str
    backend: str
    language: str
    country: str
    use_verifier: bool
    status: str = ""  # "ok", "ok_after_retry", "fallback", "refused", "not_verified"
    final_text: str = ""
    facts: dict = field(default_factory=dict)
    removed_ungrounded: list = field(default_factory=list)
    attempts: list = field(default_factory=list)
    steps: list = field(default_factory=list)  # tokens and cost per call to Claude
    cost_usd: float = 0.0  # API list price (with the claude-code backend: what it WOULD cost)
    latency_s: float = 0.0

    def to_json(self):
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


class Pipeline:
    def __init__(self, model="sonnet", backend="api", client=None):
        self.model_name = model
        self.backend = make_backend(backend, MODELS[model], client)

    # ---- bookkeeping ------------------------------------------------------

    def _record(self, result, step, calls):
        """Add the token use and cost of one step's calls to the result."""
        for call in calls:
            if call["refused"]:
                raise Refused(step)
            result.steps.append({
                "step": step,
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "cost_usd": round(call["cost_usd"], 5),
            })
            result.cost_usd += call["cost_usd"]

    def _parse(self, result, step, system, user_text, schema):
        """One call to Claude whose answer must match `schema` (structured outputs)."""
        parsed, calls = self.backend.structured(system, user_text, schema)
        self._record(result, step, calls)
        return parsed

    # ---- the three steps --------------------------------------------------

    def extract(self, result, letter):
        terms = find_terms_in_letter(letter)
        glossary_text = "\n".join(f"- {t}: {m}" for t, m in terms.items()) or "(none found)"
        user_text = (
            f"Glossary meanings for abbreviations found in this letter "
            f"(some may be false matches; use judgement):\n{glossary_text}\n\n"
            f"<letter>\n{letter}\n</letter>"
        )
        facts = self._parse(result, "extract", prompts.EXTRACT, user_text, ExtractedFacts)
        result.removed_ungrounded = checks.remove_ungrounded(facts, letter)
        result.facts = facts.model_dump()
        return facts

    def explain(self, result, facts, language, previous=None, problems=None):
        system = prompts.EXPLAIN.format(
            language=language,
            language_name=LANGUAGE_NAMES[language],
            headings="\n".join(f"## {h}" for h in fixed_text.HEADINGS[language]),
            no_warning_signs=fixed_text.NO_WARNING_SIGNS[language],
        )
        user_text = "Facts (JSON):\n" + facts.model_dump_json(indent=2)
        if previous:
            user_text += (
                f"\n\nYour previous explanation:\n{previous}\n\n"
                + prompts.REVISE.format(problems="\n".join(f"- {p}" for p in problems))
            )
        text, calls = self.backend.write_with_tools(system, user_text)
        self._record(result, "explain", calls)
        return text

    def verify(self, result, letter, explanation, language):
        system = prompts.VERIFY.format(language_name=LANGUAGE_NAMES[language])
        user_text = f"<letter>\n{letter}\n</letter>\n\n<explanation>\n{explanation}\n</explanation>"
        return self._parse(result, "verify", system, user_text, VerifierReport)

    # ---- putting it together ---------------------------------------------

    def run(self, letter, language="en", country="uk", use_verifier=True, max_attempts=2):
        result = Result(self.model_name, self.backend.name, language, country, use_verifier)
        start = time.monotonic()
        try:
            facts = self.extract(result, letter)
            draft, problems = None, []
            for attempt in range(1, max_attempts + 1):
                draft = self.explain(result, facts, language, previous=draft, problems=problems)
                problems, record = self.check(result, letter, draft, language, use_verifier)
                record["attempt"] = attempt
                result.attempts.append(record)
                if not use_verifier:
                    # Baseline for the eval: no safety net, show the first draft as it is.
                    result.status = "not_verified"
                    result.final_text = fixed_text.finish(draft, language, country)
                    break
                if not problems:
                    result.status = "ok" if attempt == 1 else "ok_after_retry"
                    result.final_text = fixed_text.finish(draft, language, country)
                    break
            else:
                result.status = "fallback"
                result.final_text = fixed_text.fallback(language, country)
        except Refused:
            result.status = "refused"
            result.final_text = fixed_text.fallback(language, country)
        result.latency_s = round(time.monotonic() - start, 1)
        result.cost_usd = round(result.cost_usd, 5)
        return result

    def check(self, result, letter, draft, language, use_verifier):
        """Run all checks on one draft. Returns (blocking problems, full record)."""
        record = {
            "explanation": draft,
            "missing_headings": checks.missing_headings(draft, language),
            "unknown_numbers": checks.unknown_numbers(draft, letter),
            "readability": readability(draft, language),  # reported, not blocking
            "verifier": None,
        }
        problems = [f"Missing heading: {h}" for h in record["missing_headings"]]
        problems += [f"The number {n} is not in the letter" for n in record["unknown_numbers"]]
        if use_verifier:
            report = self.verify(result, letter, draft, language)
            record["verifier"] = report.model_dump()
            problems += [
                f"[{p.kind}] {p.why} (explanation: {p.explanation_says!r}; letter: {p.letter_says!r})"
                for p in report.problems if p.severity == "major"
            ]
        record["blocking_problems"] = problems
        return problems, record
