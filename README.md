# Music Library Manager

A personal music library browser that serves your record collection as a public static site on GitHub Pages.

## Why

Discogs removed the ability to filter/view custom fields in their app. This project preserves your curated library data (genres, feelings, ratings, notes) in a portable format and gives you a filterable UI accessible from desktop and mobile.

## How it works

1. **collection.json** — The committed file is the source of truth for your library. It contains all albums with metadata, custom fields, and Spotify links.
2. **Build** — `build_site.py` bundles `collection.json` and `config.json` into `site/data.json`. Both are publicly readable on the deployed site.
3. **Deploy** — A GitHub Action builds and deploys to GitHub Pages on every push to main.
4. **Browse** — The site loads `data.json` and renders a filterable/sortable card grid.

## Stack

- **Python + requests** — Discogs & Spotify API integration
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
- Add albums from the UI — opens a prefilled GitHub Issue (you submit it while logged in to GitHub), processed daily by a cron job. Only issues opened by the repo owner are processed.
- Works on mobile (responsive, collapsible filter bar)

## Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| **Deploy** | Push to main, manual | Builds `site/data.json` from `collection.json` and deploys to Pages |
| **Process add-requests** | Daily cron (06:00 UTC), manual | Processes issue requests → adds to Discogs + `collection.json` (with Spotify lookup) → commits → deploys |
| **Enrich Spotify links** | Manual only | Searches Spotify for albums without a link (including previous misses), stores only confident artist + title matches, updates `collection.json` → commits → deploys |
| **Sync from Discogs** | Manual only | Pulls fresh data from Discogs, preserving repo-only fields (e.g. `spotify_url`) → commits → deploys |

## Local development

```bash
# Build and serve locally
uv run python build_site.py
python3 -m http.server 8000 --directory site
# Open http://localhost:8000
```

## Deployment setup

### Prerequisites

- Public GitHub repo at `github.com/LorenzoCavatorta/music-library-manager` (the collection, config, issues and Actions logs are all publicly readable)
- GitHub Pages enabled with "GitHub Actions" as the build source

### Secrets to configure

Go to repo Settings → Secrets and variables → Actions, and add:

| Secret | Value |
|--------|-------|
| `DISCOGS_TOKEN` | Your Discogs personal access token (Settings → Developers) |
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
