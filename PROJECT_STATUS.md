# Project Status

**Last updated:** 2026-08-03

## Completed

- [x] Static site (`site/index.html`) — DaisyUI + Tailwind, magazine grid with cover art
- [x] Passphrase unlock screen (AES-256-GCM, Web Crypto API)
- [x] Filters: search, Feeling, MyGeneres, minimum rating (multi-select)
- [x] Sorting: date added, rating, artist, year
- [x] Card layout: artist + year → title → stars + Spotify icon → tags
- [x] Mobile-responsive (collapsible filter bar)
- [x] GitHub Pages deploy workflow
- [x] Spotify integration — small themed icon on cards, links to album
- [x] Add-request system via GitHub Issues (UI form + daily cron processing)
- [x] Custom fields support in add-request form (Feeling, MyGeneres, Instruments, Rating)
- [x] Failed add-requests stay open with `needs-attention` label (no silent failures)
- [x] `collection.json` committed as source of truth (no Discogs dependency for deploys)
- [x] Sync-from-Discogs workflow (manual, preserves repo-only fields)
- [x] Enrich-Spotify workflow (manual, with rate-limit warning)
- [x] Spotify cache removed — URLs stored directly in `collection.json`
- [x] Repo pushed to `github.com/LorenzoCavatorta/music-library-manager` (private)

## TODO

- [ ] Strip Discogs disambiguation suffixes from artist names before Spotify search (e.g. "Grimes (4)" → "Grimes") — would improve match rate
- [ ] PWA manifest + service worker for offline support / "Add to Home Screen"
- [ ] Additional filters (Instruments, Highlights, year range)
- [ ] Link each card to the Discogs release page
- [ ] OpenClaw bot integration for submitting add-requests
- [ ] Multiple custom field support in filter dropdowns (multi-select)

## Architecture decisions

| Decision | Reasoning |
|----------|-----------|
| `collection.json` as source of truth | Independence from Discogs — deploys don't call external APIs; protects against Discogs dropping custom field support |
| Deploy only encrypts (no export) | Fast, no external dependencies, always uses committed state |
| Sync-from-Discogs is manual | Avoids overwriting local-only data; user decides when to pull |
| Repo-only fields preserved on sync | Any field in existing records that Discogs doesn't provide is kept automatically |
| Spotify URLs in collection (no cache) | Single source of truth; cache was only needed when rebuilding from scratch |
| Rate-limit = warning, not failure | Enrichment is incremental; partial progress is committed and re-running finishes the job |
| Failed add-requests stay open | Prevents losing requests silently; `needs-attention` label + comment guides the user |
| Static site over self-hosted | No spare hardware, security concerns about VPS |
| GitHub Pages over Netlify/Cloudflare | Free, simple, integrates with Actions |
| Client-side encryption | Site is public but data is private — no auth server needed |
| DaisyUI + Tailwind (CDN) | No build step, polished look |
| uv for Python env | Keeps project isolated from other work environments |
| GitHub Issues for add-requests | Issues-only token scope, audit trail, no merge conflicts, any client can submit |
| Token in encrypted payload | Only available after passphrase unlock; passphrase is the security boundary |
| Separate cron workflow for processing | Decouples request processing from deploy — failures are isolated |
| Plain `requests` for Spotify (not `spotipy`) | Only need 2 API calls; avoids extra dep for trivial auth+search |
| Spotify Client Credentials (not user auth) | Search API is public, no need for user login flow |
