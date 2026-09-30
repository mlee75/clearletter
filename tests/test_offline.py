"""Tests that run without an API key and cost nothing.

They check the plain-code parts (tools, checks, fixed texts) and the
pipeline's decisions (retry, fallback, refusal) using a fake Claude.
Run: python -m pytest -q
"""

from pathlib import Path
from types import SimpleNamespace

from clearletter import checks, fixed_text
from clearletter.pipeline import Pipeline
from clearletter.schemas import ExtractedFacts, Medicine, Problem, VerifierReport
from clearletter.tools import find_terms_in_letter, lookup_term, readability

ROOT = Path(__file__).resolve().parent.parent
WARFARIN_LETTER = (ROOT / "data" / "synthetic" / "syn_16.txt").read_text()


# ---- tools ---------------------------------------------------------------

def test_glossary_lookup_known_and_unknown():
    assert "three times a day" in lookup_term("TDS")
    assert "three times a day" in lookup_term("tds")
    assert "Do not guess" in lookup_term("XYZQ")


def test_glossary_scan_is_case_sensitive():
    found = find_terms_in_letter("Paracetamol 1 g QDS PRN. Take it on time.")
    assert {"QDS", "PRN", "g"} <= set(found)
    assert "ON" not in found  # the word "on" is not the abbreviation "ON"


def test_readability_simple_text_scores_easier_than_complex():
    simple = readability("Take one tablet each day. Do not stop. Call us if you feel ill.", "en")
    hard = readability(
        "Pharmacological anticoagulation necessitates meticulous international normalised ratio "
        "monitoring, notwithstanding concomitant administration of interacting medications.", "en")
    assert simple["reading_ease"] > hard["reading_ease"]
    assert simple["passed"] and not hard["passed"]
    assert "grade_level" not in readability("Prenez un comprimé par jour.", "fr")


# ---- checks --------------------------------------------------------------

def test_numbers_check_catches_changed_dose_and_invented_phone_number():
    letter = "Take 4 mg each evening. Next test on 12/10/2026."
    assert checks.unknown_numbers("Take 4 mg each evening. Next test on 12 October 2026.", letter) == []
    assert checks.unknown_numbers("Take 5 mg each evening.", letter) == ["5"]
    assert checks.unknown_numbers("Call 0800 123 456.", letter) == ["123", "456", "800"]


def test_numbers_check_ignores_list_markers_and_accepts_number_words():
    letter = "Take one tablet twice daily."
    assert checks.unknown_numbers("1. Take 1 tablet.\n2. Do this twice a day.", letter) == []


def test_numbers_check_accepts_french_decimal_comma():
    assert checks.unknown_numbers("Donnez 7,5 ml.", "Give 7.5 ml.") == []


def test_grounding_removes_invented_items():
    facts = make_facts()
    facts.medicines.append(Medicine(name="Aspirin", dose="75 mg", how_often="once a day",
                                    change="start", details="", quote="Start aspirin 75 mg"))
    removed = checks.remove_ungrounded(facts, WARFARIN_LETTER)
    assert [r["item"]["name"] for r in removed] == ["Aspirin"]
    assert [m.name for m in facts.medicines] == ["Warfarin"]


def test_every_language_and_country_has_fixed_texts():
    for language in fixed_text.LANGUAGES:
        assert len(fixed_text.HEADINGS[language]) == 5
        for country in fixed_text.COUNTRIES:
            text = fixed_text.fallback(language, country)
            assert fixed_text.DISCLAIMER[language] in text


# ---- pipeline decisions, with a fake Claude --------------------------------

GOOD_DRAFT = "\n".join(f"## {h}\nText." for h in fixed_text.HEADINGS["en"]) + "\nTake 4 mg from 6 October 2026."
BAD_DRAFT = GOOD_DRAFT + "\nTake 5 mg."  # 5 mg is the OLD dose: wrong
MAJOR = Problem(kind="dosage", severity="major", explanation_says="5 mg", letter_says="4 mg", why="wrong dose")


def make_facts():
    return ExtractedFacts(
        reader="patient", purpose="Warfarin dose change",
        findings=[], dates=[], actions=[], negatives=[], warning_signs=[], unclear=[],
        medicines=[Medicine(name="Warfarin", dose="4 mg", how_often="each evening", change="decrease",
                            details="was 5 mg", quote="take 4 mg each evening")],
    )


def fake_message(parsed=None, text="", stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason, parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        content=[SimpleNamespace(type="text", text=text)],
    )


class FakeClient:
    """Pretends to be anthropic.Anthropic(). Returns pre-written drafts and verifier reports."""

    def __init__(self, drafts, reports, refuse=False):
        self.drafts, self.reports, self.refuse = list(drafts), list(reports), refuse
        self.messages = SimpleNamespace(parse=self.parse)
        self.beta = SimpleNamespace(messages=SimpleNamespace(tool_runner=self.tool_runner))

    def parse(self, output_format, **kwargs):
        if self.refuse:
            return fake_message(stop_reason="refusal")
        if output_format is ExtractedFacts:
            return fake_message(parsed=make_facts())
        return fake_message(parsed=self.reports.pop(0))

    def tool_runner(self, **kwargs):
        return iter([fake_message(text=self.drafts.pop(0))])


def run_fake(drafts, reports, **kwargs):
    client = FakeClient(drafts, reports, kwargs.pop("refuse", False))
    return Pipeline("sonnet", client=client).run(WARFARIN_LETTER, **kwargs)


def test_passes_first_time():
    result = run_fake([GOOD_DRAFT], [VerifierReport(problems=[], summary="ok")])
    assert result.status == "ok"
    assert fixed_text.EMERGENCY[("uk", "en")] in result.final_text
    assert result.cost_usd > 0


def test_retries_once_then_passes():
    result = run_fake([BAD_DRAFT, GOOD_DRAFT],
                      [VerifierReport(problems=[MAJOR], summary="bad"), VerifierReport(problems=[], summary="ok")])
    assert result.status == "ok_after_retry"
    assert len(result.attempts) == 2


def test_falls_back_when_problems_remain():
    result = run_fake([BAD_DRAFT, BAD_DRAFT],
                      [VerifierReport(problems=[MAJOR], summary="bad")] * 2)
    assert result.status == "fallback"
    assert fixed_text.FALLBACK["en"] in result.final_text
    assert "5 mg" not in result.final_text


def test_minor_problems_do_not_block():
    minor = Problem(kind="dropped", severity="minor", explanation_says="", letter_says="ward name", why="not needed")
    result = run_fake([GOOD_DRAFT], [VerifierReport(problems=[minor], summary="fine")])
    assert result.status == "ok"


def test_numbers_check_blocks_even_if_verifier_misses_it():
    # 5 mg is in the letter (as the old dose), so the numbers check cannot see that mistake.
    # 7 mg is in no part of the letter, so the numbers check blocks it without any AI.
    invented = GOOD_DRAFT + "\nTake 7 mg."
    result = run_fake([invented, invented], [VerifierReport(problems=[], summary="looks fine")] * 2)
    assert result.status == "fallback"


def test_refusal_shows_fallback():
    result = run_fake([], [], refuse=True)
    assert result.status == "refused"
    assert fixed_text.FALLBACK["en"] in result.final_text


def test_without_verifier_shows_first_draft_unchecked():
    result = run_fake([BAD_DRAFT], [], use_verifier=False)
    assert result.status == "not_verified"
    assert "5 mg" in result.final_text  # the baseline has no safety net: that is what the eval measures
