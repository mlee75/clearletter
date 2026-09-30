"""The exact shapes of data that Claude must return.

Using "structured outputs", the API guarantees Claude's answer matches these
shapes, so the code never has to guess how to read it.

Every extracted item carries a `quote`: the exact words from the letter it
came from. The program checks each quote really is in the letter. An item
whose quote cannot be found is treated as made up and removed.
"""

from typing import List, Literal

from pydantic import BaseModel


class Finding(BaseModel):
    statement: str  # e.g. "Possible small tear of the meniscus in the left knee"
    certainty: Literal["confirmed", "possible", "ruled_out", "pending", "not_stated"]
    quote: str


class Medicine(BaseModel):
    name: str
    dose: str  # exactly as written, e.g. "90 mg"
    how_often: str  # in plain words, e.g. "twice a day"
    change: Literal["start", "stop", "continue", "increase", "decrease", "skip_dose", "other"]
    details: str  # duration, timing, "was 5 mg", tablets to use; "" if none
    quote: str


class DatedItem(BaseModel):
    what: str
    when: str  # written in full, unambiguous: "3 December 2026", "within 2 weeks"
    quote: str


class Instruction(BaseModel):
    instruction: str  # what the patient must do, or must not do
    quote: str


class ExtractedFacts(BaseModel):
    """Step 1 output: everything the patient needs, and nothing else."""
    reader: Literal["patient", "parent_or_carer", "doctor_copy_to_patient", "doctor_only"]
    purpose: str  # why the letter was sent, one sentence
    findings: List[Finding]
    medicines: List[Medicine]
    dates: List[DatedItem]
    actions: List[Instruction]
    negatives: List[Instruction]  # important "no"/"not" statements, e.g. "no fracture"
    warning_signs: List[Instruction]  # only warning signs the LETTER lists
    unclear: List[str]  # anything the extractor could not interpret safely


class Problem(BaseModel):
    kind: Literal["added", "dropped", "changed", "dosage", "date", "negation", "certainty", "advice", "urgency"]
    severity: Literal["major", "minor"]
    explanation_says: str  # "" if the problem is something dropped
    letter_says: str  # "" if the problem is something added
    why: str


class VerifierReport(BaseModel):
    """Step 3 output: the verifier's comparison of the explanation with the letter."""
    problems: List[Problem]
    summary: str
