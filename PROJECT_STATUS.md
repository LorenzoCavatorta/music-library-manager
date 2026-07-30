# Project Status

**Last updated:** 2026-07-29

## Completed

- [x] Discogs export script (`export_collection.py`) — fetches all 1109 releases with custom fields and ratings
- [x] Encryption script (`encrypt_collection.py`) — AES-256-GCM with PBKDF2
- [x] Static site (`site/index.html`) — DaisyUI + Tailwind, single-column layout
- [x] Filters: search, Feeling, MyGeneres, minimum rating
- [x] Sorting: date added, rating, artist, year
- [x] Card layout: artist (bold, centered) → title → star rating → year/label → tags
- [x] Passphrase unlock screen
- [x] GitHub Actions workflow (`.github/workflows/deploy.yml`)
- [x] Repo pushed to `github.com/LorenzoCavatorta/music-library-manager` (private)

## TODO — before it's fully live

- [ ] Delete the accidentally-created repo on `github.mpi-internal.com` (Settings → Danger Zone → Delete)
- [ ] Set GitHub secrets: `DISCOGS_TOKEN` and `PASSPHRASE`
- [ ] Enable GitHub Pages (build source: GitHub Actions)
- [ ] Trigger first deploy (push or manual workflow run)
- [ ] Verify the live site works on mobile

## In progress

### Spotify integration

Adds clickable "Open in Spotify" links to album cards. The script (`enrich_spotify.py`) searches the Spotify Search API for each album by artist+title and stores the URL in `collection.json`.

**Design choices:**
- Uses plain `requests` instead of the `spotipy` library — avoids a new dependency for two simple API calls (client credentials token + search)
- Client Credentials flow (no user login needed) — sufficient for the public Search API
- Saves progress to `collection.json` every 50 albums — avoids losing work if interrupted
- Skips albums that already have a `spotify_url` on re-runs — safe to run repeatedly
- Exits gracefully if rate-limited for >60s (saves progress before quitting)
- Request timeout of (5s connect, 10s read) to avoid hanging indefinitely

**One-time setup:**
1. Create a Spotify app at https://developer.spotify.com/dashboard (no redirect URI needed)
2. Copy Client ID and Client Secret into `.env`

**Playbook — completing the enrichment run (2026-07-31 or later):**

The first run on 2026-07-30 hit Spotify's rate limit after ~610 albums (0.1s sleep was too aggressive). The app is rate-limited until ~2026-07-31 morning.

1. Confirm rate limit has expired:
   ```
   export $(grep -v '^#' .env | xargs)
   PYTHONUNBUFFERED=1 uv run python enrich_spotify.py
   ```
   If it prints "Rate limited for Xs" and exits, wait longer or create a second Spotify app with fresh credentials.

2. If it starts processing, let it run (~2 min for 1109 albums at 0.1s/req). It will print progress and save every 50 albums.

3. After completion, re-encrypt and verify:
   ```
   export $(grep -v '^#' .env | xargs)
   uv run python encrypt_collection.py
   python3 -m http.server 8001 --directory site
   ```
   Open http://localhost:8001, unlock, and spot-check a few albums have the Spotify button.

4. If many albums show "not found", it may be due to Discogs artist name formatting (e.g. "Grimes (4)" with disambiguation numbers). A follow-up improvement would be to strip trailing `(N)` from artist names before searching.

**Known issues:**
- Discogs artist names sometimes have disambiguation suffixes like "(2)", "(4)" which don't match on Spotify — expect ~10-20% miss rate
- Spotify rate limit is per-app (not per-IP), so a second app is the workaround if throttled

## Add-request system

Allows adding albums to the library without going through Discogs directly. Designed to also support future OpenClaw bot integration.

**Flow:**
1. User submits "Add: Artist - Title" from the app UI (or any GitHub Issues client)
2. A GitHub Issue is created with label `library-addition-request`
3. Daily cron (06:00 UTC) runs `process_requests.py`: searches Discogs, adds to collection, closes issue with result
4. The deploy re-exports, re-encrypts, and publishes the updated site

**Design choices:**
- GitHub Issues as the request queue — narrow token scope (`issues` only for the browser token), built-in audit trail, no merge conflicts, works from any client
- Token bundled in encrypted payload — only accessible after passphrase unlock; scoped to `issues` permission only (cannot write code)
- Backwards-compatible payload format — `encrypt_collection.py` now outputs `{collection, gh_issues_token}` but the UI handles the old bare-array format too
- Separate workflow (`process-requests.yml`) from deploy — processing can fail without blocking normal deploys
- Future: OpenClaw bot can submit requests by opening issues via the same API, no changes needed

**Setup:**
1. Create a fine-grained PAT at github.com → Settings → Developer settings → Fine-grained tokens
   - Scope: only this repo, permission: Issues (read/write)
2. Add as repo secret: `GH_ISSUES_TOKEN`
3. Create the `library-addition-request` label in the repo (Issues → Labels → New label)

## Future ideas (not started)

- PWA manifest + service worker for offline support / "Add to Home Screen"
- Additional filters (Instruments, Highlights, year range)
- Link each card to the Discogs release page
- OpenClaw bot integration for submitting add-requests
- Multiple custom field support in filter dropdowns (multi-select)

## Architecture decisions

| Decision | Reasoning |
|----------|-----------|
| Static site over self-hosted | No spare hardware, security concerns about VPS |
| GitHub Pages over Netlify/Cloudflare | Free, simple, integrates with Actions |
| Client-side encryption | Site is public but data is private — no auth server needed |
| DaisyUI + Tailwind (CDN) | No build step, polished look, chosen over Pico CSS and Shoelace |
| uv for Python env | Keeps project isolated from other work environments |
| JSON export format | Flexible, easy to query, convertible to SQLite later if needed |
| Single-column layout | Better readability, works well on mobile |
| Plain `requests` for Spotify (not `spotipy`) | Only need 2 API calls; avoids extra dep for trivial auth+search |
| Spotify Client Credentials (not user auth) | Search API is public, no need for user login flow |
| Incremental save every 50 albums | Rate limits and network issues are real — don't lose progress |
| GitHub Issues for add-requests (not JSON file) | Issues-only token scope, audit trail, no merge conflicts, any client can submit |
| Token in encrypted payload (not hardcoded) | Only available after passphrase unlock; passphrase is the security boundary |
| Separate cron workflow for processing | Decouples request processing from deploy — failures are isolated |
