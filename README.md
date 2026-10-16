# PlugX M3U Updater

Auto-refreshed IPTV playlist built from [plugxapi.pages.dev](https://plugxapi.pages.dev/api).

Same style as sportlink `zio.m3u` (Kodi ClearKey + VLC + EXTHTTP headers).

## Raw playlist URL (after you push to GitHub)

```text
https://raw.githubusercontent.com/<YOUR_USER>/<YOUR_REPO>/main/plugx.m3u
```

Paste that into TiviMate / OTT Navigator / Kodi / any player that supports **DASH + ClearKey**.

## What it does

1. Fetches full channel list from `https://plugxapi.pages.dev/api`
2. For each channel, fetches stream credentials from `https://plugxapi.pages.dev/?id=...`
3. Writes `plugx.m3u` with:
   - `#KODIPROP` ClearKey license
   - stream headers (User-Agent, Referer, Cookie token)
   - `#EXTVLCOPT` + `#EXTHTTP` for other apps
4. GitHub Actions re-runs **every 6 hours** (token lifetime is ~6h) and also on manual button

## Setup (you do this once)

1. Create a **new empty GitHub repo** (public is easiest for raw URLs)
2. Upload everything in this folder to the repo root:
   - `script/generate_plugx.py`
   - `.github/workflows/update-playlist.yml`
   - `README.md`
   - (optional empty) `plugx.m3u`
3. In the repo go to **Actions** → enable workflows if asked
4. Open **Update PlugX Playlist** → **Run workflow**
5. Wait a few minutes. `plugx.m3u` will appear/update on `main`

### Local test

```bash
python script/generate_plugx.py
```

Needs Python 3.10+ (stdlib only, no pip packages).

## Notes

- Not every channel will play everywhere. Many streams are Jio CDN + ClearKey; your player must support both.
- Cookie token (`__hdnea__`) expires about every 6 hours — that is why Actions runs on that schedule.
- ClearKey keys are usually stable; only the CDN cookie rotates.
- If the upstream API is down, the workflow keeps the last good `plugx.m3u`.

## File layout

```text
.
├── .github/workflows/update-playlist.yml
├── script/generate_plugx.py
├── plugx.m3u          # generated
├── .last_check        # tiny status json
└── README.md
```
