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

## Future ideas (not started)

- Add cover art (Discogs API has thumbnail URLs)
- PWA manifest + service worker for offline support / "Add to Home Screen"
- Additional filters (Instruments, Highlights, year range)
- Link each card to the Discogs release page
- Periodic auto-sync (scheduled GitHub Action, e.g. weekly)
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
