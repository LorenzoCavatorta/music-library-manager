# Music Library Manager

A personal music library browser that exports your Discogs collection (including custom fields and ratings) and serves it as a passphrase-protected static site on GitHub Pages.

## Why

Discogs removed the ability to filter/view custom fields in their app. This project preserves your curated library data (genres, feelings, ratings, notes) in a portable format and gives you a filterable UI accessible from desktop and mobile.

## How it works

1. **Export** — A Python script fetches your full Discogs collection via their API, including all custom field values and ratings
2. **Encrypt** — The collection JSON is encrypted client-side with AES-256-GCM (PBKDF2 key derivation) so the static site can be hosted publicly without exposing your data
3. **Deploy** — A GitHub Action re-exports, encrypts, and deploys to GitHub Pages on every push (or manual trigger)
4. **Browse** — The site decrypts in-browser with your passphrase, then renders a filterable/sortable card list

## Stack

- **Python + requests** — Discogs API export
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
- Add albums from the UI — creates a GitHub Issue, processed daily by a cron job that searches Discogs and adds to collection
- Passphrase protection (AES-256-GCM, no server needed)
- Works on mobile (responsive, collapsible filter bar)

## Local development

```bash
# Export collection
DISCOGS_TOKEN='your_token' uv run python export_collection.py

# Encrypt for the static site
PASSPHRASE='your_passphrase' uv run python encrypt_collection.py

# Serve locally
uv run python -m http.server 8000 --directory site
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
| `GH_ISSUES_TOKEN` | Fine-grained PAT with Issues read/write on this repo (for the add-album feature) |

### Enable Pages

```bash
gh api repos/LorenzoCavatorta/music-library-manager/pages -X POST -f build_type=workflow --hostname github.com
```

### Trigger a deploy

Push to `main`, or manually trigger via Actions → "Deploy to GitHub Pages" → Run workflow.

## Updating your library

Whenever you add/rate/tag records in Discogs, just push a commit (or trigger the workflow manually) and the site will re-export and redeploy with the latest data.
