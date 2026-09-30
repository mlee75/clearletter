# What the evaluation found (v1 baseline)

The numbers are in [results.md](results.md), generated from 220 saved runs. This page is
the interpretation. Run on 30 September 2026 through the Claude Code backend: 60 minutes,
no failures, nothing charged.

## Headline

| Target (SPEC.md) | Best configuration: Sonnet + verifier | Met? |
|---|---|---|
| Must-keep facts preserved ≥ 95% | 99.5% (20 synthetic), 95.6% (20 MTSamples) | Yes |
| Dosage errors = 0 | 0 synthetic, 1 MTSamples | Almost |
| Date errors = 0 | 0 | Yes |
| **Added claims = 0** | **8 claims in 4 of 20 synthetic letters; 18 in 9 of 20 MTSamples** | **No** |
| Reading age ~11 (FK grade ≤ 6) | grade 4.2, Reading Ease 80 | Yes |
| Red-team pass rate 15/15 | 15/15 | Yes, but see below |

**The pipeline is very good at keeping what the letter says, but it adds things. Most of
those additions come from my own design, and they can be fixed.**

## 1. Which model?

- **Sonnet + verifier is the best balance:** 99.5% of facts kept, no dosage or date errors,
  the fewest added claims, 33 seconds per letter.
- **Opus** kept every fact (100%) but added slightly more claims (10, in 9 letters) and cost
  about 15% more, so there is no safety case for it here.
- **Haiku is not safe enough** for this task. Without the verifier: 2 dosage and 2 date
  errors, 20 added claims, and one invented date ("approximately 1 December 2026" for a
  review the letter only says is "in 3 months"). With the verifier it fell back to "ask your
  doctor" on 5 of 20 letters (25%). The verifier kept Haiku mostly safe by refusing, not by
  fixing.

## 2. Does the verifier help?

Yes for the serious errors, and not much for the subtle ones.

- It removed every dosage error on the synthetic letters (Haiku: 2 → 0) and cut dropped
  facts for every model (Haiku 14 → 10, Sonnet 4 → 1, Opus 2 → 0).
- It roughly halved added claims for Haiku (20 → 8) and cut them on MTSamples (28 → 18),
  but made little difference for Sonnet (10 → 8) and none for Opus (9 → 10).
- **Why it misses added claims:** the verifier *does* notice them, but it grades most of
  them "minor", and only "major" problems block (decision D6). The severity rule is where
  the leak is.
- It costs 35 to 40% more for Sonnet and Opus (API-equivalent) and adds 8 to 11 seconds per
  letter. For Haiku it more than doubles cost and time, because Haiku's drafts fail more often and get retried.

## 3. Where the added claims come from

The judge listed 128 unsupported claims across the 182 scored explanations (190 runs minus 8 fallbacks). Reading them,
they fall into four groups:

1. **Labels my schema forced (about 40%).** The extraction schema makes every medicine
   carry a `change` of start/stop/continue/... and every finding a `certainty` of
   "confirmed", "possible" and so on. There is no "the letter does not say". So the model
   writes "this is a new medicine", "no change" or "this is confirmed" when the letter says
   none of these. 37 of the 128 claims contain the word "new". **This is a design bug,
   found by the eval.**
2. **Permission turned into an instruction.** "You do not need to fast" became "do not
   fast". "Dioralyte can be used" became "use Dioralyte". "You do not need to stop any of
   your medicines" became "do not stop any of your medicines" (in French).
3. **Well-meant safety advice that is not in the letter**, mostly on the MTSamples letters
   written doctor-to-doctor: "Do not stop Dilantin on your own", "Do not start Coumadin on
   your own", "Take all your new medicines every day" (wrong for a GTN spray used only
   when needed). These sound responsible, which is exactly why they need a rule: the
   spec forbids advice that is not in the letter.
4. **Changing who does what, and doing date arithmetic** (mostly Haiku): "the GP will check
   your kidneys in 2 weeks" became "ask your doctor for a kidney test by 16 October".

Only a few added claims are dangerous on their own. But groups 2 and 3 change what a
patient might *do*, and that is the risk this project exists to measure.

## 4. Real documents are harder

On the MTSamples documents (US letters between doctors, some with errors in the source),
Sonnet + verifier kept 95.6% of facts, fell back on 3 of 20, and added 18 claims. The one
"dosage error" is a tense slip ("were picked up" instead of "to pick up"). Letters that are
not written for the patient invite the model to fill gaps with advice.

## 5. Other languages

French and Spanish kept 98.4% and 98.9% of facts (judged on an English back-translation).
The one French dosage error matters: mirtazapine "at night" became "in the evening"
(*le soir*), which is a real difference for a sedating medicine. Readability was higher than
English (Reading Ease 86 to 88). The author's own review of the 30 outputs is still pending
(`evals/human_review/`).

## 6. Red team: 15/15, which is too easy

Sonnet passed all 15 red-team letters **with and without** the verifier. It ignored the
prompt injection, gave no opinion on sertraline in pregnancy, did not answer the "can I
double my dose" question, and flagged the letter that contradicts itself about the dose. A
perfect score with no difference between conditions means the set has a ceiling effect.
The next version needs harder cases, for example injections hidden in the middle of a
clinical sentence, or advice the letter implies but does not state.

## 7. Can the judge be trusted?

I read a random sample of 12 of the 128 added claims next to their letters. I agreed with
10, found 2 borderline (for example "your place will be given to another patient" for "so
we can offer your slot to another patient"), and found no clear false positives. So the
judge is strict, but its findings are real.

## 8. Limits of this evaluation

- **The gold facts are Claude drafts** that the author has not reviewed yet, so a Claude
  model wrote the answer key and another Claude model graded against it.
- **One run per condition.** Differences of one or two errors between conditions are within
  noise. There is no variance estimate yet.
- **Small sets:** 20 letters per condition, 15 red-team letters.
- **Costs** are what the same tokens would cost on the API, including Claude Code's own
  overhead. **Latency** includes starting a Claude Code process for every call.
- **Back-translation** is a screening check, not a substitute for a native speaker.

## 9. Proposed v2 (not yet applied)

1. Schema: add "not stated" to `change` and "stated" to `certainty`, and tell the writer to
   mention a change or a level of certainty only when the letter states it.
2. Writer prompt: keep permissions as permissions ("you do not need to"), keep who does
   what, never compute dates, never add protective advice that is not in the letter.
3. Verifier: treat any added advice as blocking, whatever severity it is given.
4. Re-run parts 1 and 2 (160 jobs, about 45 minutes on the subscription) and compare v1
   with v2 in a new table.
