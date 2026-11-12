"""A small mutation trial (L6 item 7, ADOPT row L3a, SPEC 3.4: a trial with a keep-or-cut rule).

It changes ONE thing at a time in a throw-away copy of the package (never in `src/`), runs the tests that are meant to
cover that code, and lists the changes no test noticed (survivors). A survivor is either a real gap in the tests or a
change that does not alter behaviour; the person running the trial reads each one and writes down which.

    python scripts/mutation_trial.py --out mutation.json \
        src/leadforge/retention.py:1-400:tests/test_l6_forget.py,tests/test_l6_purge.py

A target is `file:first_line-last_line:test_file,test_file`. Mutations: comparison operators swapped, `and`/`or`
swapped, `not` removed, booleans flipped, integers plus one, `+`/`-` swapped, `return x` made `return None`, a call
statement removed. This is not the vendor tool the plan names (mutmut does not run on Windows); see the slice file.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
       ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}


class Mutator(ast.NodeTransformer):
    """Counts the candidate changes in a tree; with `target` set, applies the one numbered `target`."""

    def __init__(self, lo: int, hi: int, target: int | None = None):
        self.lo, self.hi, self.target = lo, hi, target
        self.n = 0
        self.found: list[tuple[int, int, str]] = []

    def _hit(self, node, what: str) -> bool:
        line = getattr(node, "lineno", 0)
        if not (self.lo <= line <= self.hi):
            return False
        idx = self.n
        self.n += 1
        self.found.append((idx, line, what))
        return idx == self.target

    def visit_Compare(self, node):
        self.generic_visit(node)
        op = type(node.ops[0])
        if op in CMP and self._hit(node, f"{op.__name__} -> {CMP[op].__name__}"):
            node.ops[0] = CMP[op]()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._hit(node, "and <-> or"):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit(node, "not removed"):
            return node.operand
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            if self._hit(node, f"{node.value} -> {not node.value}"):
                return ast.copy_location(ast.Constant(not node.value), node)
        elif isinstance(node.value, int) and self._hit(node, f"{node.value} -> {node.value + 1}"):
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, (ast.Add, ast.Sub)) and self._hit(node, "+ <-> -"):
            node.op = ast.Sub() if isinstance(node.op, ast.Add) else ast.Add()
        return node

    def visit_Return(self, node):
        self.generic_visit(node)
        if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
            if self._hit(node, "return x -> return None"):
                return ast.copy_location(ast.Return(ast.Constant(None)), node)
        return node

    def visit_Expr(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call) and self._hit(node, "call statement removed"):
            return ast.copy_location(ast.Pass(), node)
        return node


def run_tests(pkg_parent: Path, tests: list[str], timeout: int) -> str:
    env = dict(os.environ, PYTHONPATH=str(pkg_parent), LEADFORGE_NO_UI="1")
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-x", "-q", *tests], cwd=ROOT,
                           env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "killed"   # a change that makes the code hang is noticed
    return "survived" if r.returncode == 0 else "killed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--out", default="mutation.json")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0, help="only the first N changes per target (a smoke run)")
    a = ap.parse_args()
    started = time.time()
    results = []
    with tempfile.TemporaryDirectory(prefix="lf-mut-") as td:
        pkg_parent = Path(td) / "src"
        shutil.copytree(ROOT / "src" / "leadforge", pkg_parent / "leadforge", ignore=shutil.ignore_patterns("__pycache__"))
        probe = subprocess.run([sys.executable, "-c", "import leadforge; print(leadforge.__file__)"], cwd=ROOT, capture_output=True,
                               text=True, env=dict(os.environ, PYTHONPATH=str(pkg_parent)))
        if Path(probe.stdout.strip()).parent != pkg_parent / "leadforge":
            print("FAIL: the tests would not run against the copy:", probe.stdout, probe.stderr)
            return 2
        for spec in a.targets:
            rel, span, tests = spec.split(":", 2)
            lo, hi = (int(x) for x in span.split("-"))
            tests_l = tests.split(",")
            dst = pkg_parent / "leadforge" / Path(rel).relative_to("src/leadforge")
            original = dst.read_text(encoding="utf-8")
            if run_tests(pkg_parent, tests_l, a.timeout) != "survived":
                print(f"FAIL: {rel}: the tests do not pass on the unchanged copy")
                return 2
            counter = Mutator(lo, hi)
            counter.visit(ast.parse(original))
            todo = counter.found[: a.limit or None]
            print(f"{rel}:{lo}-{hi}: {len(counter.found)} changes", flush=True)
            for idx, line, what in todo:
                tree = ast.parse(original)
                m = Mutator(lo, hi, target=idx)
                new = ast.fix_missing_locations(m.visit(tree))
                dst.write_text(ast.unparse(new), encoding="utf-8")
                status = run_tests(pkg_parent, tests_l, a.timeout)
                results.append({"file": rel, "line": line, "change": what, "status": status})
                if status == "survived":
                    print(f"  SURVIVED {rel}:{line} {what}", flush=True)
            dst.write_text(original, encoding="utf-8")
    killed = sum(r["status"] == "killed" for r in results)
    summary = {"changes": len(results), "killed": killed, "survived": len(results) - killed,
               "minutes": round((time.time() - started) / 60, 1), "results": results}
    Path(a.out).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"MUTATION {summary['changes']} changes, {killed} killed, {summary['survived']} survived, {summary['minutes']} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
