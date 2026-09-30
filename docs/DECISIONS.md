# Design decisions

Each decision below records what was chosen, what else was considered, and why.
Written in plain language so every choice can be explained in an interview.

## D1. Client SDK with the tool runner, not the Agent SDK (Phase 2)

**Choice:** the pipeline uses the Anthropic Client SDK (`anthropic` for Python):
structured outputs for steps 1 and 3, and the SDK's tool runner for step 2.

**Considered:** the Claude Agent SDK (`claude-agent-sdk`).

**Why:** the Agent SDK's own documentation describes it as Claude Code packaged as a
library, with built-in tools to read and write files, run commands and search the web.
clearletter needs the opposite: a fixed three-step pipeline where the model sees only
the letter and two small tools. Anthropic's guidance is to start with the simplest option
that works, and a workflow where code controls the order of steps is simpler and safer
than an open-ended agent. A web search tool would also let the model bring in outside
medical facts, which safety rule S3 forbids. The Agent SDK is used where it fits:
testing the packaged Skill in Phase 4.

## D2. Three steps, and the writer never sees the letter

**Choice:** (1) extract facts as JSON, (2) write the explanation **from the JSON only**,
(3) a separate verifier compares the explanation with the **original letter**.

**Why:** if the writer only has the facts, anything it adds that is not in the facts is
easy to spot. The verifier reads the original letter, so it can also catch mistakes that
step 1 made. A mistake has to get past two independent readings before a patient sees it.

## D3. Every extracted fact carries a quote, checked by code

**Choice:** each extracted item includes the exact words it came from. Plain Python
checks that the quote really is in the letter and removes the item if it is not.

**Why:** this is a cheap, reliable check against the extractor making things up. It costs
nothing and never changes its mind.

## D4. Plain-code checks next to the AI verifier

**Choice:** three checks run in plain Python on every draft:
- **Numbers check:** every number in the explanation must appear in the letter. This
  catches a changed dose, a wrong date or an invented phone number.
- **Headings check:** all five sections are present.
- **Readability:** reported, but it does not block, because readability formulas only
  measure sentence and word length and are not proof of understanding (see SPEC.md).

**Why:** an AI verifier is good at meaning (a lost "not", advice that sounds reasonable
but is new) but can miss things. Code is certain about the simple things. The offline
tests include a case where the AI verifier misses an invented dose and the numbers check
still blocks it.

**Known limit:** the numbers check cannot see an old dose written as if it were the new
one, because the old dose is also in the letter. That one is left to the verifier and is
tested in the eval.

## D5. The emergency text, disclaimer and fallback are fixed, not generated

**Choice:** `clearletter/fixed_text.py` holds these texts in EN/FR/ES, and the code adds
them to every output. The model is told never to write phone numbers.

**Why:** these are the parts where an error does the most harm. A fixed text cannot invent
urgency, drop a number or give the wrong country's number. Language and country are separate
settings, because a Spanish speaker living in the UK needs UK numbers.

## D6. One retry, then "ask your doctor"

**Choice:** if a draft has a blocking problem, the writer gets one retry with the list of
problems. If the retry also fails, the patient sees only the fallback message.

**Why:** retrying repairs most small mistakes, and stopping after one retry keeps cost
and delay bounded. When the tool cannot explain a letter safely, saying nothing is safer
than a partly wrong explanation. Only "major" problems block; "minor" ones are recorded.

## D7. Glossary: code looks it up first, Claude can look it up again

**Choice:** before step 1, code finds every glossary abbreviation in the letter and gives
the meanings to the extractor. In step 2, Claude can call `glossary_lookup` itself. For an
unknown term, the tool says "do not guess" rather than returning nothing.

**Why:** doing the lookup in code means it can never be skipped. Offering the tool as well
shows the agentic pattern, and gives a safe answer for terms not in the glossary.

## D8. No automatic model fallback on refusals

**Choice:** if Claude declines a request (`stop_reason: "refusal"`), the patient sees the
fallback message and the eval counts it. Anthropic's server-side `fallbacks` option, which
would quietly retry on another model, is **not** enabled.

**Why:** Phase 3 compares Haiku, Sonnet and Opus. If a refused request silently switched
model, the comparison would be mixed up. For a patient, "please ask your doctor" is a safe
result.

## D9. Model settings

- Models: `claude-haiku-4-5`, `claude-sonnet-5-5`, `claude-opus-5-5` (IDs and prices checked
  on 30 September 2026, stored in `clearletter/config.py`).
- Sonnet 5.5 and Opus 5.5 always think before answering. Their `effort` is set to
  `medium` for both so the comparison is fair (Opus 5.5 defaults to medium, Sonnet 5.5
  to high). Haiku 4.5 runs without extended thinking.
- No `temperature` setting: the newest models do not accept one.
- The verifier uses the same model as the writer, so each model is tested on its own.
  A stronger verifier with a cheaper writer is a possible Phase 3 experiment.
