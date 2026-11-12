"""Count what `mutmut results --all true` printed, only for the mutants the trial asked for, per module and per outcome.

    python .github/mutation/summarize.py results.txt "leadforge.retention.*" "leadforge.db.x_peek_schema_version__mutmut_*" ...

Reads lines of the form `    leadforge.retention.x_foo__mutmut_3: killed`. Prints a markdown table (also the survivors by name) and
exits 0; the keep-or-cut call is a person's, written in the slice file.
"""
from __future__ import annotations

import fnmatch
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUTCOMES = ("killed", "survived", "no tests", "timeout", "suspicious", "skipped", "not checked")


def summarize(text: str, patterns: list[str]) -> tuple[dict[str, Counter], list[str]]:
    per_module: dict[str, Counter] = defaultdict(Counter)
    survivors: list[str] = []
    for line in text.splitlines():
        name, sep, status = line.strip().rpartition(": ")
        if not sep or "__mutmut_" not in name:
            continue
        if not any(fnmatch.fnmatch(name, p) for p in patterns):
            continue
        module = name.partition("__mutmut_")[0].rsplit(".", 1)[0]
        status = status.strip()
        per_module[module][status if status in OUTCOMES else "other"] += 1
        if status == "survived":
            survivors.append(name)
    return per_module, survivors


def render(per_module: dict[str, Counter], survivors: list[str]) -> str:
    cols = (*OUTCOMES, "other")
    lines = ["| module | total | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    totals: Counter = Counter()
    for module in sorted(per_module):
        c = per_module[module]
        totals += c
        lines.append(f"| {module} | {sum(c.values())} | " + " | ".join(str(c[k]) for k in cols) + " |")
    lines.append(f"| **all** | {sum(totals.values())} | " + " | ".join(str(totals[k]) for k in cols) + " |")
    lines += ["", f"survivors: {len(survivors)}"] + [f"- {s}" for s in sorted(survivors)]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    per_module, survivors = summarize(Path(argv[1]).read_text(encoding="utf-8"), argv[2:])
    if not per_module:
        print("NO MUTANTS MATCHED the patterns: nothing was measured")
        return 1
    print(render(per_module, survivors))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
