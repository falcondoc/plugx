#!/usr/bin/env python3
"""
PlugX M3U generator
Pulls a fresh playlist from premiumplugx.top (live cookies + keys)
and keeps the same working format the source uses so players play all channels.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.request
from pathlib import Path

SOURCE_URL = "https://premiumplugx.top/mylive/playlist.php"

_cwd = Path.cwd()
if (_cwd / "script").is_dir():
    ROOT = _cwd
else:
    ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "plugx.m3u"
META_OUTPUT = ROOT / ".last_check"
ROOT.mkdir(parents=True, exist_ok=True)

# Match the UA that premiumplugx itself uses (players that work on source expect this)
USER_AGENT = "PlayTV/7.1.5 (Linux;Android 8.1.0) ExoPlayerLib/2.11.7"
TIMEOUT = 45


def http_get(url: str, timeout: int = TIMEOUT) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_extinf(line: str) -> dict:
    out = {"id": "", "name": "", "logo": "", "group": "General"}
    m = re.search(r'tvg-id="([^"]*)"', line)
    if m:
        out["id"] = m.group(1)
    m = re.search(r'tvg-name="([^"]*)"', line)
    if m:
        out["name"] = m.group(1)
    m = re.search(r'tvg-logo="([^"]*)"', line)
    if m:
        out["logo"] = m.group(1)
    m = re.search(r'group-title="([^"]*)"', line)
    if m:
        out["group"] = m.group(1)
    if "," in line:
        tail = line.split(",", 1)[1].strip()
        if tail:
            out["name"] = tail
    return out


def extract_cookie(exthttp_line: str) -> str:
    if not exthttp_line.startswith("#EXTHTTP:"):
        return ""
    raw = exthttp_line[len("#EXTHTTP:") :].strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return str(data.get("cookie") or data.get("Cookie") or "").strip()
    except json.JSONDecodeError:
        m = re.search(r'"cookie"\s*:\s*"([^"]*)"', raw, re.I)
        if m:
            return m.group(1)
    return ""


def extract_license_key(line: str) -> str:
    if "license_key=" in line:
        return line.split("license_key=", 1)[1].strip()
    return ""


def parse_source_m3u(text: str) -> list[dict]:
    channels: list[dict] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        meta = parse_extinf(line)
        license_key = ""
        cookie = ""
        mpd = ""
        j = i + 1
        while j < n:
            l2 = lines[j].strip()
            if l2.startswith("#EXTINF:"):
                break
            if l2.startswith("#KODIPROP:") and "license_key=" in l2:
                license_key = extract_license_key(l2)
            elif l2.startswith("#EXTHTTP:"):
                cookie = extract_cookie(l2)
            elif l2 and not l2.startswith("#"):
                mpd = l2
                j += 1
                break
            j += 1
        i = j
        if not mpd or not license_key:
            continue
        channels.append(
            {
                "id": meta["id"] or mpd,
                "name": meta["name"] or "Channel",
                "logo": meta["logo"],
                "group": meta["group"] or "General",
                "mpd": mpd,
                "clearkey": license_key,
                "cookie": cookie,
            }
        )
    return channels


def build_entry(ch: dict) -> list[str]:
    """Mirror premiumplugx format exactly — that is what plays all channels."""
    cid = str(ch.get("id") or "")
    name = str(ch.get("name") or f"Channel {cid}").replace("\n", " ").strip()
    logo = str(ch.get("logo") or "").strip()
    group = str(ch.get("group") or "General").replace("\n", " ").strip()
    mpd = str(ch.get("mpd") or "").strip()
    ck = str(ch.get("clearkey") or "").strip()
    cookie = str(ch.get("cookie") or "").strip()

    if not mpd or not ck:
        return []

    # Source-style EXTHTTP: only cookie (players that work on source use this)
    if cookie:
        exthttp = json.dumps({"cookie": cookie}, ensure_ascii=False, separators=(",", ":"))
    else:
        exthttp = "{}"

    lines = [
        f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}", {name}',
        "#KODIPROP:inputstream.adaptive.manifest_type=mpd",
        "#KODIPROP:inputstream.adaptive.license_type=clearkey",
        f"#KODIPROP:inputstream.adaptive.license_key={ck}",
        f"#EXTVLCOPT:http-user-agent={USER_AGENT}",
        f"#EXTHTTP:{exthttp}",
        mpd,
    ]
    return lines


def generate_m3u(channels: list[dict]):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "#EXTM3U",
        f"#DATE:- {now}",
        "# Source: premiumplugx.top (live cookies)",
        f"# Channels: {len(channels)}",
        "# Auto-refreshed by GitHub Actions",
        "",
    ]
    written = 0
    with_cookie = 0
    for ch in channels:
        entry = build_entry(ch)
        if not entry:
            continue
        lines.extend(entry)
        written += 1
        if ch.get("cookie"):
            with_cookie += 1
    lines[3] = f"# Channels: {written}"
    return "\n".join(lines) + "\n", written, with_cookie


def main() -> int:
    t0 = time.time()
    print(f"Fetching source playlist: {SOURCE_URL}")
    try:
        raw = http_get(SOURCE_URL)
    except Exception as e:
        print(f"FATAL: source fetch failed: {e}")
        return 1

    print(f"Source bytes: {len(raw)}")
    channels = parse_source_m3u(raw)
    print(f"Parsed channels: {len(channels)}")
    if not channels:
        print("FATAL: zero channels parsed")
        return 1

    text, written, with_cookie = generate_m3u(channels)
    OUTPUT.write_text(text, encoding="utf-8")
    META_OUTPUT.write_text(
        json.dumps(
            {
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "source": SOURCE_URL,
                "parsed": len(channels),
                "written": written,
                "with_cookie": with_cookie,
                "seconds": round(time.time() - t0, 1),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT} ({written} entries, {with_cookie} with cookie) in {round(time.time()-t0,1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
