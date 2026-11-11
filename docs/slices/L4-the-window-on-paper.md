# L4 The window on paper
## Carried over, to do first
(a) DEFECT, fix it, do not retry it: `tests/test_enrich_speed.py::test_validate_emails_parallel_matches_serial_and_is_faster` fails now and then on
wall-clock time. CI run 43045072218 (2026-11-11, slice/L2 pull request) needed a second attempt: on attempt 1 the job
`windows-latest · py3.13` failed with `AssertionError: pooled validation took 0.55s ... expected well under the serial 0.8s`
(`assert 0.5512016000000131 < 0.4`, line 123). The test asserts a fixed elapsed bound on a shared runner. Replace the clock
assertion with something that does not depend on it (for example each call overlapping another, by count of concurrent calls).
(b) Left out of L3c because they sat in L2 files: the unused dependencies `tenacity` and `rich` (declared, never imported), and the
`gainlev_leadgen` skeleton rename (`PURPOSES` in `src/leadforge/draft/skeletons.py`, `data/skeletons/gainlev_leadgen.yaml`).
(c) `skills/send-outreach/SKILL.md` points at three files of the `generate-leads` skill (`outreach.md`, `drafting.md`, `troubleshooting.md`; lines 15, 16, 28, 52, 60), so installed alone it cannot open its guardrail detail.
