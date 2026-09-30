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

import anthropic

from . import checks, fixed_text, prompts
from .config import MAX_TOKENS, MODELS
from .schemas import ExtractedFacts, VerifierReport
from .tools import find_terms_in_letter, glossary_lookup, readability, readability_check

LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish"}


class Refused(Exception):
    """Claude declined to answer (stop_reason "refusal"). We show the fallback."""


@dataclass
class Result:
    """Everything about one run: the output, and what was checked along the way."""
    model: str
    language: str
    country: str
    use_verifier: bool
    status: str = ""  # "ok", "ok_after_retry", "fallback", "refused", "not_verified"
    final_text: str = ""
    facts: dict = field(default_factory=dict)
    removed_ungrounded: list = field(default_factory=list)
    attempts: list = field(default_factory=list)
    steps: list = field(default_factory=list)  # tokens and cost per API step
    cost_usd: float = 0.0
    latency_s: float = 0.0

    def to_json(self):
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


class Pipeline:
    def __init__(self, model="sonnet", client=None):
        self.model_name = model
        self.cfg = MODELS[model]
        self.client = client or anthropic.Anthropic()

    # ---- bookkeeping ------------------------------------------------------

    def _record(self, result, step, message):
        """Add one API response's token use and cost to the result."""
        if message.stop_reason == "refusal":
            raise Refused(step)
        usage = message.usage
        cost = self.cfg.cost(usage.input_tokens, usage.output_tokens)
        result.steps.append({
            "step": step,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(cost, 5),
        })
        result.cost_usd += cost

    def _parse(self, result, step, system, user_text, schema):
        """One API call whose answer must match `schema` (structured outputs)."""
        message = self.client.messages.parse(
            model=self.cfg.model_id,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_format=schema,
            **self.cfg.extra,
        )
        self._record(result, step, message)
        return message.parsed_output

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
        # The tool runner lets Claude call our tools as many times as it needs,
        # then returns its final answer. max_iterations stops endless loops.
        runner = self.client.beta.messages.tool_runner(
            model=self.cfg.model_id,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=[glossary_lookup, readability_check],
            messages=[{"role": "user", "content": user_text}],
            max_iterations=8,
            **self.cfg.extra,
        )
        final = None
        for message in runner:
            self._record(result, "explain", message)
            final = message
        return "".join(block.text for block in final.content if block.type == "text").strip()

    def verify(self, result, letter, explanation, language):
        system = prompts.VERIFY.format(language_name=LANGUAGE_NAMES[language])
        user_text = f"<letter>\n{letter}\n</letter>\n\n<explanation>\n{explanation}\n</explanation>"
        return self._parse(result, "verify", system, user_text, VerifierReport)

    # ---- putting it together ---------------------------------------------

    def run(self, letter, language="en", country="uk", use_verifier=True, max_attempts=2):
        result = Result(self.model_name, language, country, use_verifier)
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
