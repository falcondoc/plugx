#!/usr/bin/env python3
"""
PlugX M3U generator
Fetches channel list + per-channel credentials from plugxapi.pages.dev
and writes a Kodi/VLC/OTT-friendly M3U (same style as sportlink zio.m3u).

Refresh every ~6 hours via GitHub Actions (token window is 6h).
"""

from __future__ import annotations

import json
import concurrent.futures
import datetime as dt
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------- CONFIG ----------
LIST_URL = "https://plugxapi.pages.dev/api"
CHANNEL_URL = "https://plugxapi.pages.dev/?id={id}"

# Prefer CWD repo root when run as `python script/generate_plugx.py` from repo root
# (GitHub Actions does exactly that). Fall back to script-relative parent.
_cwd = Path.cwd()
if (_cwd / "script").is_dir():
    ROOT = _cwd
else:
    ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "plugx.m3u"
META_OUTPUT = ROOT / ".last_check"
ROOT.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Premium Plugx"
REFERER = "https://www.jiotv.com/"
ORIGIN = "https://www.jiotv.com"

# How many channels to resolve in parallel
WORKERS = 16
# HTTP timeouts
TIMEOUT = 15
# Skip channels that fail credential fetch
SKIP_ON_ERROR = True
# Optional: only keep these groups (empty = all)
GROUP_FILTER: list[str] = []
# Optional: max channels (0 = no limit) useful for testing
MAX_CHANNELS = 0
# ----------------------------


def http_get(url: str, timeout: int = TIMEOUT) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_list() -> list[dict]:
    raw = http_get(LIST_URL)
    data = json.loads(raw)
    if not isinstance(data, list):
        raise RuntimeError("Unexpected /api response (not a list)")
    return data


def fetch_channel(channel_id: str) -> dict | None:
    url = CHANNEL_URL.format(id=urllib.parse.quote(str(channel_id)))
    try:
        raw = http_get(url)
        data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("error"):
        return None
    mpd = (data.get("mpd_url") or data.get("url") or "").strip()
    ck = (data.get("clearkey") or "").strip()
    if not mpd or not ck:
        return None
    return data


# late import for quote
import urllib.parse  # noqa: E402


def resolve_all(meta_list: list[dict]) -> list[dict]:
    if GROUP_FILTER:
        allow = {g.lower() for g in GROUP_FILTER}
        meta_list = [c for c in meta_list if str(c.get("group") or "").lower() in allow]

    if MAX_CHANNELS and MAX_CHANNELS > 0:
        meta_list = meta_list[:MAX_CHANNELS]

    results: list[dict] = []
    total = len(meta_list)
    done = 0

    def work(item: dict) -> dict | None:
        cid = str(item.get("id") or "").strip()
        if not cid:
            return None
        full = fetch_channel(cid)
        if not full:
            return None
        # prefer live payload fields, fall back to list meta
        full.setdefault("id", cid)
        full.setdefault("name", item.get("name") or f"Channel {cid}")
        full.setdefault("group", item.get("group") or "General")
        full.setdefault("logo", item.get("logo") or "")
        full.setdefault("type", item.get("type") or "dash")
        full.setdefault("user_agent", item.get("user_agent") or USER_AGENT)
        return full

    print(f"Resolving credentials for {total} channels (workers={WORKERS})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(work, item): item for item in meta_list}
        for fut in concurrent.futures.as_completed(futs):
            done += 1
            if done % 50 == 0 or done == total:
                print(f"  progress {done}/{total}")
            try:
                row = fut.result()
            except Exception:
                row = None
            if row:
                results.append(row)

    # stable order: original list order
    order = {str(c.get("id")): i for i, c in enumerate(meta_list)}
    results.sort(key=lambda x: order.get(str(x.get("id")), 10**9))
    return results


def cookie_from(channel: dict) -> str:
    headers = channel.get("headers") or {}
    if isinstance(headers, dict):
        c = headers.get("cookie") or headers.get("Cookie") or ""
        if c:
            return str(c).strip()
    # sometimes flat
    return str(channel.get("cookie") or "").strip()


def clearkey_from(channel: dict) -> str:
    ck = channel.get("clearkey")
    if isinstance(ck, dict):
        # {kid: key}
        parts = [f"{k}:{v}" for k, v in ck.items() if k and v]
        return ",".join(parts)
    if isinstance(ck, str) and ck.strip():
        return ck.strip()
    kid = channel.get("keyId") or channel.get("key_id")
    key = channel.get("key")
    if kid and key:
        return f"{kid}:{key}"
    return ""


def mpd_from(channel: dict) -> str:
    return (channel.get("mpd_url") or channel.get("url") or "").strip()


def build_entry(channel: dict) -> list[str]:
    cid = str(channel.get("id") or "")
    name = str(channel.get("name") or f"Channel {cid}").replace("\n", " ").strip()
    logo = str(channel.get("logo") or "").strip()
    group = str(channel.get("group") or "General").replace("\n", " ").strip()
    mpd = mpd_from(channel)
    ck = clearkey_from(channel)
    cookie = cookie_from(channel)
    ua = str(channel.get("user_agent") or USER_AGENT).strip() or USER_AGENT

    if not mpd or not ck:
        return []

    # stream_headers for Kodi inputstream.adaptive
    # format: key=value&key=value
    header_parts = [
        f"User-Agent={ua}",
        f"Referer={REFERER}",
        f"Origin={ORIGIN}",
    ]
    if cookie:
        header_parts.append(f"Cookie={cookie}")
    stream_headers = "&".join(header_parts)

    # EXTHTTP JSON (used by some Android IPTV apps / NS Player style)
    exthttp = {
        "User-Agent": ua,
        "Referer": REFERER,
        "Origin": ORIGIN,
    }
    if cookie:
        exthttp["Cookie"] = cookie
    exthttp_json = json.dumps(exthttp, ensure_ascii=False, separators=(",", ": "))

    lines = [
        f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}",{name}',
        "#KODIPROP:inputstream=inputstream.adaptive",
        "#KODIPROP:inputstream.adaptive.manifest_type=mpd",
        "#KODIPROP:inputstream.adaptive.license_type=clearkey",
        f"#KODIPROP:inputstream.adaptive.license_key={ck}",
        f"#KODIPROP:inputstream.adaptive.stream_headers={stream_headers}",
        f"#EXTVLCOPT:http-user-agent={ua}",
        f"#EXTVLCOPT:http-referrer={REFERER}",
    ]
    if cookie:
        lines.append(f"#EXTVLCOPT:http-cookie={cookie}")
    lines.append(f"#EXTHTTP:{exthttp_json}")
    lines.append(mpd)
    lines.append("")  # blank line between entries
    return lines


def generate_m3u(channels: list[dict]) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "#EXTM3U",
        f"#DATE:- {now}",
        "# Source: plugxapi.pages.dev",
        f"# Channels: {len(channels)}",
        "# Auto-refreshed by GitHub Actions (~every 6 hours)",
        "",
    ]
    written = 0
    for ch in channels:
        entry = build_entry(ch)
        if not entry:
            continue
        lines.extend(entry)
        written += 1
    # update header count
    lines[3] = f"# Channels: {written}"
    return "\n".join(lines) + "\n", written


def main() -> int:
    t0 = time.time()
    print("Fetching channel list...")
    meta = fetch_list()
    print(f"List size: {len(meta)}")

    channels = resolve_all(meta)
    print(f"With credentials: {len(channels)}")

    text, written = generate_m3u(channels)
    OUTPUT.write_text(text, encoding="utf-8")
    META_OUTPUT.write_text(
        json.dumps(
            {
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "list_total": len(meta),
                "with_credentials": written,
                "seconds": round(time.time() - t0, 1),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT} ({written} entries) in {round(time.time()-t0,1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
