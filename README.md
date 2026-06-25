# 80Grade status wall

A simple, at-a-glance "is everything green right now" wall over the 16
healthchecks.io checks — the positive counterpart to the alert-only (Pushover)
observability. Current state only (no 90-day trend, by design).

## How it works

A GitHub Action runs every ~10 min, fetches the healthchecks.io **Management API**
with a read-only key (kept in a repo secret — never in the browser), renders a
static `index.html`, and publishes it to GitHub Pages. The wall is **purely
HC-driven**: every check the API returns is shown, and any check not in the
grouping falls into "Other" — so a newly-added HC check appears automatically.

Hosting is deliberately **off-corpus**: the status wall must not die with the
thing it's watching.

## Files

| File | What |
|---|---|
| `render_status_wall.py` | Fetches/parses the HC API, writes `index.html`. |
| `status-wall.yml` | The GitHub Action (goes in `.github/workflows/`). |
| `checks_sample.json` | A real API response, used as the test fixture. |
| `test_render_status_wall.py` | Tests (status mapping, overdue math, grouping). |
| `index.html` | A sample render of the current state. |

## Setup (one-time)

1. **Create a small dedicated repo** (e.g. `wainetam/80grade-status`) — keeps the
   main private repo private. Put `render_status_wall.py` at its root and
   `status-wall.yml` at `.github/workflows/status-wall.yml`.
2. **Add the secret:** repo Settings → Secrets and variables → Actions → New
   repository secret → name `HC_API_KEY`, value = your **read-only** HC API key.
3. **Enable Pages:** repo Settings → Pages → Source = **GitHub Actions**.
4. **First build:** Actions tab → `status-wall` → Run workflow. The wall lands at
   `https://wainetam.github.io/80grade-status/`.

## Things to know

- **GitHub cron is best-effort** — it can lag 5–15 min on shared runners. The page
  shows its own "Updated <time>", so any staleness is visible. If you want tighter,
  more reliable freshness, a Cloudflare Worker cron is the swap.
- **Meta-observability gap:** if the Action itself stops, the wall silently freezes
  on its last (green) render. Optional fix: have the renderer ping a healthchecks
  check (`status-wall-render`) on success, so HC alerts if the wall's own updater
  dies. (Not wired yet — say the word.)
- **Privacy:** the Pages URL is public. The wall exposes job names + up/down only —
  no data, no credentials. If even that's too much, swap Pages for a token-gated
  host (Cloudflare Access / Netlify password).
- **The info dot (ⓘ)** on PSA / daily-capture / cold-storage marks freshness-only
  checks (green = ran, not necessarily succeeded). It disappears once those checks
  are made status-aware.

## Local testing

```
python3 test_render_status_wall.py
python3 render_status_wall.py --input checks_sample.json --output index.html
```
