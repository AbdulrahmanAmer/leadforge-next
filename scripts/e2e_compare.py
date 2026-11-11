"""Side-by-side of two normalized fake-campaign results (written by e2e_fake_campaign.py as result.json).

    python scripts/e2e_compare.py <old result.json> <new result.json> [--out compare.md]

Per exported tab: rows only in old, only in new, and changed cells (rows keyed by the first column, or 'Business' on
Leads/Drafts); the commands with exit code and digest counts; the guard's refused outside calls; the requests the
fake web server saw. It lists differences only; the reason for each is written by a person next to this output.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def table(rows):
    if not rows:
        return [], {}
    head, body = rows[0], rows[1:]
    key = head.index("Business") if "Business" in head else 0
    out = {}
    for r in body:
        out.setdefault(r[key], dict(zip(head, r)))
    return head, out


def diff_tab(name, old, new, lines):
    ho, to = table(old)
    hn, tn = table(new)
    lines.append(f"### Tab `{name}`  (old {len(to)} rows, new {len(tn)} rows)")
    if ho != hn:
        lines.append(f"- columns only in old: {[c for c in ho if c not in hn]}; only in new: {[c for c in hn if c not in ho]}")
    only_o, only_n = sorted(set(to) - set(tn)), sorted(set(tn) - set(to))
    lines.append(f"- rows only in old: {only_o or 'none'}")
    lines.append(f"- rows only in new: {only_n or 'none'}")
    n_changed = 0
    for k in sorted(set(to) & set(tn)):
        for col in [c for c in hn if c in ho]:
            if to[k][col] != tn[k][col]:
                n_changed += 1
                lines.append(f"- CHANGED `{k}` / `{col}`: old={to[k][col]!r:.160} -> new={tn[k][col]!r:.160}")
    lines.append(f"- changed cells: {n_changed}")
    lines.append("")


def _csv_state(a, b):
    if a == b:
        return "identical"
    if sorted(map(tuple, a)) == sorted(map(tuple, b)):
        return "same rows, different order"
    return f"DIFFERENT ({len(set(map(tuple, a)) ^ set(map(tuple, b)))} rows not in both)"


def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, f"{pre}{k}.")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, f"{pre}{i}.")
    else:
        yield pre.rstrip("."), o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--out")
    a = ap.parse_args()
    o, n = load(a.old), load(a.new)
    L = ["## Commands (exit code, digest ok/counts)"]
    so = {s["step"]: s for s in o["steps"]}
    sn = {s["step"]: s for s in n["steps"]}
    for k in dict.fromkeys([*so, *sn]):
        for lab, s in (("old", so.get(k)), ("new", sn.get(k))):
            if s is None:
                L.append(f"- {k:<14} {lab}: (not run)")
                continue
            d = s["digest"] or {}
            L.append(f"- {k:<14} {lab}: exit={s['exit']} ok={d.get('ok')} counts={json.dumps(d.get('counts'))[:260]} warnings={json.dumps(d.get('warnings'), ensure_ascii=False)[:260]}")
    L += ["", "## Exported tabs"]
    for tab in dict.fromkeys([*o["tabs"], *n["tabs"]]):
        if tab not in o["tabs"] or tab not in n["tabs"]:
            L.append(f"### Tab `{tab}`: only in {'old' if tab in o['tabs'] else 'new'}\n")
            continue
        diff_tab(tab, o["tabs"][tab], n["tabs"][tab], L)
    L.append("## CSV files")
    for f in dict.fromkeys([*o["csv"], *n["csv"]]):
        L.append(f"- {f}: {_csv_state(o['csv'].get(f, []), n['csv'].get(f, []))} (old {len(o['csv'].get(f, []))} rows, new {len(n['csv'].get(f, []))} rows)")
    L.append("\n## report.json (changed leaves)")
    fo, fn = dict(flat(o.get("report") or {})), dict(flat(n.get("report") or {}))
    ch = [k for k in dict.fromkeys([*fo, *fn]) if fo.get(k) != fn.get(k)]
    L += [f"- `{k}`: old={fo.get(k)!r:.120} new={fn.get(k)!r:.120}" for k in ch] or ["- identical"]
    L.append("\n## Refused outside calls (kind, host, caller): count")
    co, cn = Counter(map(tuple, ([r[0], r[1], r[3]] for r in o["refused"]))), Counter(map(tuple, ([r[0], r[1], r[3]] for r in n["refused"])))
    for k in dict.fromkeys([*co, *cn]):
        L.append(f"- {k}: old {co.get(k, 0)}, new {cn.get(k, 0)}")
    L.append(f"- TOTAL: old {len(o['refused'])}, new {len(n['refused'])}")
    L.append("\n## Requests the fake web server saw (set difference)")
    ro, rn = set(o["requests"]), set(n["requests"])
    L.append(f"- only old: {sorted(ro - rn) or 'none'}")
    L.append(f"- only new: {sorted(rn - ro) or 'none'}")
    text = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
