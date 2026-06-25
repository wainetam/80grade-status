#!/usr/bin/env python3
"""Render the 80Grade status wall (current state) from the healthchecks.io Management API.

The wall is purely HC-driven: every check the API returns is shown. Slugs not in
GROUPS fall into "Other" so a newly-added HC check appears automatically (no
hand-maintained job list to drift).

Usage:
  # From a saved API response (local / testing):
  python3 render_status_wall.py --input checks_sample.json --output index.html
  # Fetch live (production / GitHub Action):
  HC_API_KEY=... python3 render_status_wall.py --fetch --output index.html
"""
import argparse
import html
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

HC_API_URL = "https://healthchecks.io/api/v1/checks/"

# slug -> group, in display order. Unmapped slugs land in "Other".
GROUPS = [
    ("Core data · the moat", [
        "80grade-heartbeat-cron", "daily-capture-heartbeat", "psa-heartbeat",
        "ebay-orchestrator-heartbeat", "capture-130point-heartbeat",
    ]),
    ("Backups & sync", [
        "sync-b2-heartbeat", "coldstorage-heartbeat", "sync-onetouch-heartbeat",
    ]),
    ("Alert monitors", [
        "monitor-pricing-moves-heartbeat", "monitor-prospect-rankings-heartbeat",
        "monitor-psa-pop-moves-heartbeat", "monitor-prospect-news-heartbeat",
        "monitor-mlb-id-resolution-heartbeat",
    ]),
    ("Infra & maintenance", [
        "check-disk-space-heartbeat", "transactions-heartbeat", "retry-stuck-urls-heartbeat",
    ]),
]

# Public display labels (fallback = slug). Third-party source names are
# neutralized for the public page (eBay / 130point / PSA / B2 / MLB -> generic
# functional names) and the raw slug line is omitted from each card, so the page
# doesn't advertise which external sources the pipeline depends on.
LABELS = {
    "80grade-heartbeat-cron": "Orchestrator watchdog",
    "daily-capture-heartbeat": "Daily-capture chain",
    "psa-heartbeat": "Population capture",
    "ebay-orchestrator-heartbeat": "Marketplace orchestrator",
    "capture-130point-heartbeat": "Sold-comps capture",
    "sync-b2-heartbeat": "Cloud backup sync",
    "coldstorage-heartbeat": "Cold storage",
    "sync-onetouch-heartbeat": "OneTouch sync",
    "monitor-pricing-moves-heartbeat": "Pricing moves",
    "monitor-prospect-rankings-heartbeat": "Prospect rankings",
    "monitor-psa-pop-moves-heartbeat": "Population-move monitor",
    "monitor-prospect-news-heartbeat": "Prospect news",
    "monitor-mlb-id-resolution-heartbeat": "Player id resolution",
    "check-disk-space-heartbeat": "Disk space",
    "transactions-heartbeat": "Transactions",
    "retry-stuck-urls-heartbeat": "Retry stuck URLs",
}

# HC pings that fire on freshness (ran) not success (succeeded) -> show an info dot.
# Emptied 2026-06-25: psa / daily-capture / coldstorage are now SUCCESS-gated —
# cycle_heartbeat.sh is status-aware (pings <slug>/fail on a failed sentinel) and
# the chains ping /fail on their own failure path, so green now means COMPLETED
# and no caveat dot is warranted. The mechanism stays for any future freshness-
# only check (add its slug back here to re-enable the dot).
FRESHNESS_ONLY = set()

# hc status -> (css_key, word, color)
STATE = {
    "up": ("up", "up", "#22c55e"),
    "grace": ("late", "late", "#f97316"),
    "down": ("down", "down", "#ef4444"),
    "new": ("new", "new", "#9ca3af"),
    "paused": ("paused", "paused", "#9ca3af"),
    "started": ("up", "running", "#22c55e"),
}
UNKNOWN_STATE = ("new", "unknown", "#9ca3af")


def fmt_delta(seconds):
    seconds = int(abs(seconds))
    if seconds < 60:
        return f"{seconds}s"
    m = seconds // 60
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m" if m else f"{h}h"
    d, h = divmod(h, 24)
    return f"{d}d {h}h" if h else f"{d}d"


def parse_iso(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_checks(args):
    if args.fetch:
        key = os.environ.get("HC_API_KEY")
        if not key:
            sys.exit("HC_API_KEY env var is required with --fetch")
        req = urllib.request.Request(HC_API_URL, headers={"X-Api-Key": key})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["checks"]
    with open(args.input) as f:
        return json.load(f)["checks"]


def detail_for(check, now):
    """Right-hand detail line: overdue duration when late/down, else relative last ping."""
    status = check.get("status")
    last = parse_iso(check.get("last_ping"))
    nxt = parse_iso(check.get("next_ping"))
    if status in ("grace", "down") and nxt:
        return "overdue " + fmt_delta((now - nxt).total_seconds())
    if status == "new" or last is None:
        return "never pinged"
    return fmt_delta((now - last).total_seconds()) + " ago"


def render(checks, now):
    by_slug = {c["slug"]: c for c in checks}
    seen = set()
    counts = {"up": 0, "late": 0, "down": 0, "new": 0, "paused": 0}

    def card(c):
        css_key, word, color = STATE.get(c.get("status"), UNKNOWN_STATE)
        counts[css_key] = counts.get(css_key, 0) + 1
        label = LABELS.get(c["slug"], c.get("name") or c["slug"])
        fresh = c["slug"] in FRESHNESS_ONLY
        detail = detail_for(c, now)
        info = (' <span class="info" title="green = ran on time, not yet '
                'success-verified">&#9432;</span>') if fresh else ""
        late = css_key in ("late", "down")
        return (
            f'<div class="card s-{css_key}">'
            f'<span class="dot"></span>'
            f'<div class="meta"><div class="label">{html.escape(label)}{info}</div></div>'
            f'<div class="right"><div class="word">{word}</div>'
            f'<div class="detail{" late" if late else ""}">{html.escape(detail)}</div></div>'
            f'</div>'
        )

    sections = []
    for title, slugs in GROUPS:
        cards = []
        for slug in slugs:
            c = by_slug.get(slug)
            if c:
                cards.append(card(c))
                seen.add(slug)
        if cards:
            sections.append((title, cards))

    leftover = [c for c in checks if c["slug"] not in seen]
    if leftover:
        sections.append(("Other (ungrouped)",
                         [card(c) for c in sorted(leftover, key=lambda x: x["slug"])]))

    banner_color = "#ef4444" if counts.get("down") else (
        "#f97316" if counts.get("late") else (
            "#9ca3af" if counts.get("new") or counts.get("paused") else "#22c55e"))
    parts = []
    if counts.get("up"):
        parts.append(f'{counts["up"]} up')
    for k, w in (("late", "late"), ("down", "down"), ("new", "new"), ("paused", "paused")):
        if counts.get(k):
            parts.append(f'{counts[k]} {w}')
    summary = " · ".join(parts) or "no checks"

    body = []
    for title, cards in sections:
        body.append(f'<div class="group"><h2>{html.escape(title)}</h2>'
                    f'<div class="grid">{"".join(cards)}</div></div>')

    updated = now.strftime("%Y-%m-%d %H:%M UTC")
    return PAGE.replace("{{BANNER_COLOR}}", banner_color) \
              .replace("{{SUMMARY}}", html.escape(summary)) \
              .replace("{{UPDATED}}", updated) \
              .replace("{{BODY}}", "".join(body))


PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>80Grade · system status</title>
<style>
:root{--bg:#0d0f13;--card:#161a20;--bd:#252a32;--tx:#e6e9ee;--mut:#8b929c;--up:#22c55e;--late:#f97316;--down:#ef4444;--new:#9ca3af}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:28px 18px}
.wrap{max-width:760px;margin:0 auto}
h1{font-size:18px;font-weight:600;margin:0 0 16px}
.banner{display:flex;align-items:center;gap:12px;border:1px solid {{BANNER_COLOR}}55;background:{{BANNER_COLOR}}1a;border-radius:12px;padding:13px 16px;margin-bottom:14px}
.banner .b-dot{width:13px;height:13px;border-radius:50%;background:{{BANNER_COLOR}};flex:none}
.banner .b-txt{font-weight:600;color:{{BANNER_COLOR}}}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-bottom:22px}
.legend span{display:flex;align-items:center;gap:6px}
.legend i{width:11px;height:11px;border-radius:50%;display:inline-block}
.group{margin-bottom:20px}
.group h2{font-size:12px;font-weight:600;color:var(--mut);text-transform:none;margin:0 0 8px;letter-spacing:.02em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px}
.card{display:flex;align-items:center;gap:11px;border:1px solid var(--bd);border-radius:9px;padding:10px 12px;background:var(--card)}
.card .dot{width:13px;height:13px;border-radius:50%;flex:none}
.s-up .dot{background:var(--up)} .s-late .dot{background:var(--late)} .s-down .dot{background:var(--down)} .s-new .dot{background:var(--new)} .s-paused .dot{background:var(--new)}
.s-up{border-color:#22c55e44} .s-late{border-color:#f9731666;background:#f973160f} .s-down{border-color:#ef444466;background:#ef44440f} .s-new{border-color:var(--bd)}
.meta{min-width:0;flex:1}
.label{font-size:14px;font-weight:500;display:flex;align-items:center;gap:6px}
.info{color:var(--mut);font-style:normal;cursor:help}
.slug{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.right{text-align:right;white-space:nowrap}
.word{font-size:12px;font-weight:600}
.s-up .word{color:var(--up)} .s-late .word{color:var(--late)} .s-down .word{color:var(--down)} .s-new .word,.s-paused .word{color:var(--new)}
.detail{font-size:11px;color:var(--mut)} .detail.late{color:var(--late)}
.foot{color:var(--mut);font-size:12px;margin-top:18px}
</style></head>
<body><div class="wrap">
<h1>80Grade · system status</h1>
<div class="banner"><span class="b-dot"></span><span class="b-txt">{{SUMMARY}}</span></div>
<div class="legend">
<span><i style="background:var(--up)"></i>up</span>
<span><i style="background:var(--late)"></i>late</span>
<span><i style="background:var(--down)"></i>down</span>
<span><i style="background:var(--new)"></i>new / paused</span>
<span>&#9432; green = ran on time, not yet success-verified</span>
</div>
{{BODY}}
<div class="foot">Updated {{UPDATED}} · auto-refreshes every 10 min</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="path to a saved /api/v1/checks/ JSON response")
    ap.add_argument("--fetch", action="store_true", help="fetch live (needs HC_API_KEY)")
    ap.add_argument("--output", default="index.html")
    args = ap.parse_args()
    if not args.fetch and not args.input:
        ap.error("provide --input FILE or --fetch")
    checks = load_checks(args)
    out = render(checks, datetime.now(timezone.utc))
    with open(args.output, "w") as f:
        f.write(out)
    print(f"wrote {args.output} ({len(checks)} checks)")


if __name__ == "__main__":
    main()
