#!/usr/bin/env python3
"""
marathi.m3u — fixed 14 Marathi channels from Axion stalker (genre 22).

Exact order, root group (no Marathi folder). Auto-refreshed by GitHub Actions.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

PORTAL = "http://195.26.87.217:80/"
MAC = "00:1A:79:20:6F:F3"
GENRE_ID = "22"  # MARATHI
UA = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
XUA = "Model: MAG254; Link: Ethernet"
LOAD = urljoin(PORTAL, "server/load.php")

_cwd = Path.cwd()
ROOT = _cwd if (_cwd / "script").is_dir() else Path(__file__).resolve().parent.parent
OUT = ROOT / "marathi.m3u"
META = ROOT / ".last_check_marathi"

KEEP_ORDER = [
    "Zee Marathi FHD",
    "Colors Marathi FHD",
    "Star Pravah FHD",
    "Star Pravah Picture FHD",
    "Sony Marathi HD",
    "Sun Marathi FHD",
    "DD Sahyadri",
    "ABP Majha FHD",
    "Zee 24 Taas FHD",
    "TV9 Marathi FHD",
    "News18 Marathi FHD",
    "Saam TV HD",
    "Jai Maharashtra FHD",
    "Shemaroo Marathibana",
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


KEEP_NORMS = [norm(x) for x in KEEP_ORDER]


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "X-User-Agent": XUA,
        "Accept": "*/*",
        "Connection": "Keep-Alive",
        "Cookie": f"mac={MAC}; stb_lang=en; timezone=GMT",
    })
    r = s.get(LOAD, params={"type": "stb", "action": "handshake", "JsHttpRequest": "1-xml"}, timeout=15)
    r.raise_for_status()
    token = r.json()["js"]["token"]
    s.headers["Authorization"] = f"Bearer {token}"
    s.headers["Cookie"] = f"mac={MAC}; stb_lang=en; timezone=GMT; token={token}"
    return s


def get_channels(s: requests.Session) -> list:
    r = s.get(LOAD, params={"type": "itv", "action": "get_all_channels", "JsHttpRequest": "1-xml", "p": 1}, timeout=30)
    r.raise_for_status()
    data = r.json().get("js", {})
    chs = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    return [c for c in chs if str(c.get("tv_genre_id") or c.get("genre_id") or "") == GENRE_ID]


def resolve_stream(s: requests.Session, cmd: str):
    if not cmd:
        return None
    try:
        r = s.get(LOAD, params={
            "type": "itv",
            "action": "create_link",
            "cmd": cmd if cmd.startswith(("ffmpeg ", "http", "auto ")) else f"ffmpeg {cmd}",
            "series": "",
            "forced_storage": "undefined",
            "disable_ad": "0",
            "download": "0",
            "force_ch_link_check": "0",
            "JsHttpRequest": "1-xml",
        }, timeout=12)
        stream = r.json().get("js", {}).get("cmd") or r.json().get("js", {}).get("stream")
        if stream and stream.startswith("ffmpeg "):
            stream = stream[7:].strip()
        if stream and stream.startswith("auto "):
            stream = stream[5:].strip()
        if stream and stream.startswith("http"):
            return stream
    except Exception:
        pass
    m = re.search(r"(https?://\S+)", cmd)
    return m.group(1) if m else None


def match_keep(display: str):
    n = norm(display)
    for idx, kn in enumerate(KEEP_NORMS):
        if n == kn:
            return idx
    for idx, kn in enumerate(KEEP_NORMS):
        if kn in n or n in kn:
            if "picture" in kn and "picture" not in n:
                continue
            if "picture" in n and "picture" not in kn:
                continue
            if "bk" in n:
                continue
            return idx
    return None


def build():
    s = session()
    channels = get_channels(s)
    print(f"Marathi channels found: {len(channels)}")

    slots = {}
    for i, ch in enumerate(channels, 1):
        cid = str(ch.get("id") or "")
        name = (ch.get("name") or ch.get("title") or f"CH-{cid}").strip()
        display = re.sub(r"^MR:\s*", "", name)
        idx = match_keep(display)
        if idx is None:
            continue
        if idx in slots:
            continue
        logo = ch.get("logo") or ch.get("logo_url") or ""
        cmd = ch.get("cmd") or ""
        stream = resolve_stream(s, cmd)
        if not stream:
            print(f"  skip (no stream): {display}")
            continue
        slots[idx] = (display, cid, logo, stream)
        print(f"  keep [{idx}] {display}")
        time.sleep(0.06)

    lines = [
        "#EXTM3U",
        f"#DATE:- {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "# Marathi root list (filtered sequence)",
        f"# Channels: {len(slots)}",
        "# Auto-refreshed by GitHub Actions",
        "",
    ]
    for idx in range(len(KEEP_ORDER)):
        if idx not in slots:
            print(f"  MISSING slot {idx}: {KEEP_ORDER[idx]}")
            continue
        display, cid, logo, stream = slots[idx]
        logo_attr = f' tvg-logo="{logo}"' if logo else ""
        lines.append(f'#EXTINF:-1 tvg-id="{cid}"{logo_attr} group-title="",{display}')
        lines.append(stream)

    meta = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "portal": PORTAL,
        "mac": MAC,
        "genre_id": GENRE_ID,
        "found": len(channels),
        "written": len(slots),
        "order": KEEP_ORDER,
    }
    return "\n".join(lines) + "\n", meta


def main() -> int:
    text, meta = build()
    OUT.write_text(text, encoding="utf-8")
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({meta['written']} channels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
