#!/usr/bin/env python3
"""Tests for render_status_wall.py — run: python3 test_render_status_wall.py"""
import copy
import json
import os
from datetime import datetime, timedelta, timezone

import render_status_wall as r

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime(2026, 6, 25, 18, 10, tzinfo=timezone.utc)


def load():
    with open(os.path.join(HERE, "checks_sample.json")) as f:
        return json.load(f)["checks"]


def test_all_checks_render_and_summary():
    html = r.render(load(), NOW)
    assert html.count('class="card') == 16, "every check must appear (purely HC-driven)"
    assert '15 up · 1 new' in html
    # OneTouch is 'new' -> never pinged, grey
    assert 'never pinged' in html
    assert 's-new' in html


def test_overdue_for_late_and_down():
    checks = copy.deepcopy(load())
    for c in checks:
        if c["slug"] == "retry-stuck-urls-heartbeat":
            c["status"] = "grace"
            c["next_ping"] = (NOW - timedelta(minutes=23)).isoformat()
        if c["slug"] == "ebay-orchestrator-heartbeat":
            c["status"] = "down"
            c["next_ping"] = (NOW - timedelta(hours=2, minutes=14)).isoformat()
    html = r.render(checks, NOW)
    assert 's-late' in html and 's-down' in html
    assert 'overdue 23m' in html
    assert 'overdue 2h 14m' in html
    assert '13 up · 1 late · 1 down · 1 new' in html


def test_freshness_dot_only_on_three():
    html = r.render(load(), NOW)
    # info glyph appears exactly for psa / daily-capture / coldstorage
    assert html.count('class="info"') == 3


def test_unmapped_check_lands_in_other():
    checks = load() + [{"name": "brand-new-job", "slug": "brand-new-job",
                        "status": "up", "last_ping": NOW.isoformat(),
                        "next_ping": (NOW + timedelta(days=1)).isoformat()}]
    html = r.render(checks, NOW)
    assert 'Other (ungrouped)' in html
    assert 'brand-new-job' in html


def test_relative_last_ping():
    assert r.fmt_delta(45) == "45s"
    assert r.fmt_delta(23 * 60) == "23m"
    assert r.fmt_delta(2 * 3600 + 14 * 60) == "2h 14m"
    assert r.fmt_delta(3 * 86400 + 9 * 3600) == "3d 9h"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
