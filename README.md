# Music Library Manager

A personal music library browser that serves your record collection as a passphrase-protected static site on GitHub Pages.

## Why

Discogs removed the ability to filter/view custom fields in their app. This project preserves your curated library data (genres, feelings, ratings, notes) in a portable format and gives you a filterable UI accessible from desktop and mobile.

## How it works

1. **collection.json** — The committed file is the source of truth for your library. It contains all albums with metadata, custom fields, and Spotify links.
2. **Encrypt** — The collection is encrypted client-side with AES-256-GCM (PBKDF2 key derivation) so the static site can be hosted publicly without exposing your data.
3. **Deploy** — A GitHub Action encrypts and deploys to GitHub Pages on every push to main.
4. **Browse** — The site decrypts in-browser with your passphrase, then renders a filterable/sortable card grid.

## Stack

- **Python + requests** — Discogs & Spotify API integration
- **cryptography (Python)** — AES-GCM encryption at build time
- **Web Crypto API (browser)** — client-side decryption
- **DaisyUI + Tailwind CSS (CDN)** — UI framework, no build step
- **GitHub Pages** — free static hosting
- **GitHub Actions** — automated build/deploy pipeline
- **uv** — Python environment management

## Custom fields from Discogs

| Field | Purpose |
|-------|---------|
| Feeling | Mood/vibe tag used to filter when picking something to listen to |
| MyGeneres | Personal genre classification (independent of Discogs genres) |
| MyGeneresAttribute | Genre sub-attributes |
| Generes Detail | Detailed genre breakdown |
| Instruments | Notable instruments |
| Highlights | Standout tracks or moments |
| Notes | Free-form notes |

## Features

- Search by artist or title
- Filter by Feeling, MyGeneres, minimum rating (multi-select)
- Sort by date added, rating, artist, or year
- Cover art grid layout with editorial typography
- Spotify links on album cards (small icon, blends with theme)
- Add albums from the UI — creates a GitHub Issue, processed daily by a cron job
- Passphrase protection (AES-256-GCM, no server needed)
- Works on mobile (responsive, collapsible filter bar)

## Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| **Deploy** | Push to main, manual | Encrypts `collection.json` and deploys to Pages |
| **Process add-requests** | Daily cron (06:00 UTC), manual | Processes issue requests → adds to Discogs + `collection.json` (with Spotify lookup) → commits → deploys |
| **Enrich Spotify links** | Manual only | Searches Spotify for albums missing a URL, updates `collection.json` → commits → deploys |
| **Sync from Discogs** | Manual only | Pulls fresh data from Discogs, preserving repo-only fields (e.g. `spotify_url`) → commits → deploys |

## Local development

```bash
# Encrypt and serve locally
PASSPHRASE='your_passphrase' uv run python encrypt_collection.py
python3 -m http.server 8000 --directory site
# Open http://localhost:8000 and enter your passphrase
```

## Deployment setup

### Prerequisites

- Private GitHub repo at `github.com/LorenzoCavatorta/music-library-manager`
- GitHub Pages enabled with "GitHub Actions" as the build source

### Secrets to configure

Go to repo Settings → Secrets and variables → Actions, and add:

| Secret | Value |
|--------|-------|
| `DISCOGS_TOKEN` | Your Discogs personal access token (Settings → Developers) |
| `PASSPHRASE` | The passphrase used to encrypt/decrypt the collection |
| `GH_ISSUES_TOKEN` | Fine-grained PAT with Issues read/write on this repo |
| `SPOTIFY_CLIENT_ID` | Spotify app Client ID (developer.spotify.com/dashboard) |
| `SPOTIFY_CLIENT_SECRET` | Spotify app Client Secret |

### Enable Pages

```bash
gh api repos/LorenzoCavatorta/music-library-manager/pages -X POST -f build_type=workflow --hostname github.com
```

### Trigger a deploy

Push to `main`, or manually trigger via Actions → "Deploy to GitHub Pages" → Run workflow.

## Updating your library

- **Add from the UI**: Submit an add-request from the app. The daily cron processes it, adds to Discogs and `collection.json`.
- **Edit in Discogs directly**: Run the "Sync from Discogs" workflow manually to pull changes back.
- **Enrich Spotify links**: Run the "Enrich Spotify links" workflow manually (handles rate limiting gracefully — re-run until complete).
