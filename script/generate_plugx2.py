#!/usr/bin/env python3
"""Generate plugx2.m3u from allinonereborn jtv33 (working proxy-key pattern)."""
from __future__ import annotations
import datetime as dt
import urllib.request
from pathlib import Path

SOURCE = "https://allinonereborn2.online/jiotv-m3u/jtv33.m3u8"
_cwd = Path.cwd()
ROOT = _cwd if (_cwd / "script").is_dir() else Path(__file__).resolve().parent.parent
OUT = ROOT / "plugx2.m3u"

def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="ignore")

def main() -> int:
    raw = http_get(SOURCE)
    lines = raw.splitlines()
    channels = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        block = [line]
        j = i + 1
        url = ""
        while j < n:
            l2 = lines[j].strip()
            if l2.startswith("#EXTINF:") or l2.startswith("#=======") or l2.startswith("# ======="):
                break
            if l2 and not l2.startswith("#"):
                url = l2
                block.append(l2)
                j += 1
                break
            if l2:
                block.append(l2)
            j += 1
        i = j
        if url and any("license_key=" in x for x in block):
            channels.append(block)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "#EXTM3U",
        f"#DATE:- {now}",
        "# Source: allinonereborn2.online/jtv33 (proxy keys + cookie on URL)",
        f"# Channels: {len(channels)}",
        "# plugx2 - auto-refreshed",
        "",
    ]
    for b in channels:
        out.extend(b)
        out.append("")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(channels)} channels)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
