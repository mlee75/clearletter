# clearletter

> **Prototype. Not a medical device. Not for clinical use.**

Claude turns a medical letter into a faithful, plain-language explanation in the
patient's own language. The core of the project is **safety evaluation**: proving that
the explanation adds nothing, drops nothing and changes nothing.

**Status:** Phase 1 of 5 (spec and gold set). The full README comes in Phase 5.

- [SPEC.md](SPEC.md): what the tool must do and the safety rules it is tested against
- [DATA.md](DATA.md): where every letter comes from, and licences
- `python review.py`: the tool for writing the hand-made "must-keep facts" (gold set)
