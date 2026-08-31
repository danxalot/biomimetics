#!/usr/bin/env python3
"""
BiOS Dashboard Generator (Layer 4 — human view, Cloudflare-ready)

Builds a single self-contained HTML dashboard from the partitioned vault:
partition counts, the life/legal (ombudsman/SAR) tracker up top because it's the
highest-stakes, and recent notes per partition. No external assets — deployable
straight to Cloudflare Pages (or opened locally).

Reuses generate_overview.collect() so there is ONE source of collection logic.
Output: <vault>/_generated/dashboard.html   (excluded from memory sync)
"""

import os
import html
import importlib.util
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_overview():
    spec = importlib.util.spec_from_file_location(
        "gen_overview", os.path.join(_HERE, "generate_overview.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def esc(s: str) -> str:
    return html.escape(str(s or ""))


def render(recs, ts: str) -> str:
    tops = {}
    for r in recs:
        tops.setdefault(r["top"], []).append(r)

    legal = [r for r in recs if any(p.startswith("life/legal") for p in r["partitions"])]

    cards = "".join(
        f'<div class="card"><div class="n">{len(v)}</div><div class="l">{esc(k)}</div></div>'
        for k, v in sorted(tops.items(), key=lambda kv: -len(kv[1]))
    )

    def rows(items, limit=None):
        items = sorted(items, key=lambda x: x["date"], reverse=True)
        if limit:
            items = items[:limit]
        return "".join(
            f'<tr><td class="d">{esc(r["date"])}</td>'
            f'<td>{esc(r["title"])}</td>'
            f'<td class="p">{esc(r["primary"])}</td>'
            f'<td class="s">{esc(r["status"])}</td></tr>'
            for r in items
        )

    legal_rows = rows(legal) or '<tr><td colspan="4" class="muted">No legal notes yet.</td></tr>'
    recent_rows = rows(recs, limit=40)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BiOS Memory Dashboard</title>
<style>
:root {{ --bg:#0f1115; --panel:#171a21; --line:#252a34; --txt:#e6e9ef; --mut:#8a93a3; --accent:#6ea8fe; }}
*{{box-sizing:border-box}} body{{margin:0;background:#0f1115;color:#e6e9ef;font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:28px}}
h1{{font-size:22px;margin:0 0 4px}} .stamp{{color:#8a93a3;font-size:13px;margin-bottom:24px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px}}
.card{{background:#171a21;border:1px solid #252a34;border-radius:12px;padding:16px 22px;min-width:110px}}
.card .n{{font-size:28px;font-weight:700}} .card .l{{color:#8a93a3;font-size:13px;text-transform:capitalize}}
section{{background:#171a21;border:1px solid #252a34;border-radius:12px;padding:18px 20px;margin-bottom:22px}}
section h2{{margin:0 0 12px;font-size:16px}} .legal h2{{color:#ffd4a3}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid #252a34;vertical-align:top}}
th{{color:#8a93a3;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
td.d{{color:#8a93a3;white-space:nowrap;font-variant-numeric:tabular-nums}} td.p{{color:#6ea8fe;white-space:nowrap}}
td.s{{color:#8a93a3}} .muted{{color:#8a93a3}} .foot{{color:#8a93a3;font-size:12px;margin-top:18px}}
</style></head><body><div class="wrap">
<h1>BiOS Memory Dashboard</h1>
<div class="stamp">Auto-generated from the partitioned vault · {esc(ts)} · {len(recs)} notes</div>
<div class="cards">{cards}</div>
<section class="legal"><h2>⚖️ Life / Legal — Ombudsman · Complaints · SAR ({len(legal)})</h2>
<table><thead><tr><th>Date</th><th>Note</th><th>Partition</th><th>Status</th></tr></thead>
<tbody>{legal_rows}</tbody></table></section>
<section><h2>Recent notes (all partitions)</h2>
<table><thead><tr><th>Date</th><th>Note</th><th>Partition</th><th>Status</th></tr></thead>
<tbody>{recent_rows}</tbody></table></section>
<div class="foot">Derived view · rebuilt each pipeline run · do not hand-edit.</div>
</div></body></html>
"""


def main():
    go = _load_overview()
    recs = go.collect()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = go.OUT_DIR / "dashboard.html"
    go.write(out, render(recs, ts))
    print(f"Dashboard written: {out} ({len(recs)} notes)")


if __name__ == "__main__":
    main()
