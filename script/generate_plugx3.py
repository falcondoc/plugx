#!/usr/bin/env python3
"""
plugx3 — hybrid failover playlist

Primary: allinonereborn jtv33 (proxy keys + cookie on URL) — full playback
Fallback: Geo jiotv_cf (static keys + token on URL) — when primary missing a channel
Special:  Zee Marathi HD always taken from primary (Geo's copy is broken)

Auto-refreshed by GitHub Actions.
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.request
from pathlib import Path

PRIMARY_URL = "https://allinonereborn2.online/jiotv-m3u/jtv33.m3u8"
FALLBACK_URL = "https://raw.githubusercontent.com/qwerty180506/Geo/main/jiotv_cf.m3u"

_cwd = Path.cwd()
ROOT = _cwd if (_cwd / "script").is_dir() else Path(__file__).resolve().parent.parent
OUT = ROOT / "plugx3.m3u"
META = ROOT / ".last_check_plugx3"

FORCE_PRIMARY = {
    "zeemarathihd",
}


def http_get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def norm_name(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def parse_extinf_name(line: str) -> str:
    m = re.search(r'tvg-name="([^"]*)"', line, re.I)
    if m and m.group(1).strip():
        return m.group(1).strip()
    if "," in line:
        return line.split(",", 1)[1].strip()
    return ""


def parse_extinf_id(line: str) -> str:
    m = re.search(r'tvg-id="([^"]*)"', line, re.I)
    return m.group(1).strip() if m else ""


def parse_m3u_blocks(text: str) -> list:
    lines = text.splitlines()
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        block = [line]
        name = parse_extinf_name(line)
        cid = parse_extinf_id(line)
        url = ""
        j = i + 1
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
        if not url:
            continue
        joined = "\n".join(block)
        if "license_key=" not in joined and ".mpd" not in url:
            continue
        out.append(
            {
                "name": name or f"Channel {cid}",
                "norm": norm_name(name) if name else norm_name(cid),
                "id": cid,
                "block": block,
            }
        )
    return out


def build():
    print(f"Fetching primary: {PRIMARY_URL}")
    primary_raw = http_get(PRIMARY_URL)
    primary = parse_m3u_blocks(primary_raw)
    print(f"  primary channels: {len(primary)}")

    print(f"Fetching fallback: {FALLBACK_URL}")
    try:
        fallback_raw = http_get(FALLBACK_URL)
        fallback = parse_m3u_blocks(fallback_raw)
        print(f"  fallback channels: {len(fallback)}")
    except Exception as e:
        print(f"  fallback failed: {e}")
        fallback = []

    by_norm_primary = {c["norm"]: c for c in primary if c["norm"]}
    by_norm_fallback = {c["norm"]: c for c in fallback if c["norm"]}

    ordered_norms = []
    seen = set()
    for c in primary:
        k = c["norm"]
        if k and k not in seen:
            ordered_norms.append(k)
            seen.add(k)
    for c in fallback:
        k = c["norm"]
        if k and k not in seen:
            ordered_norms.append(k)
            seen.add(k)

    final_blocks = []
    from_primary = 0
    from_fallback = 0
    forced = 0

    for k in ordered_norms:
        use_primary = k in by_norm_primary
        if k in FORCE_PRIMARY:
            use_primary = True
            if k in by_norm_primary:
                forced += 1

        if use_primary and k in by_norm_primary:
            final_blocks.append(by_norm_primary[k]["block"])
            from_primary += 1
        elif k in by_norm_fallback:
            final_blocks.append(by_norm_fallback[k]["block"])
            from_fallback += 1
        elif k in by_norm_primary:
            final_blocks.append(by_norm_primary[k]["block"])
            from_primary += 1

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        "#EXTM3U",
        f"#DATE:- {now}",
        "# plugx3 hybrid failover",
        f"# Primary: allinonereborn jtv33 ({from_primary} ch)",
        f"# Fallback: Geo jiotv_cf ({from_fallback} ch)",
        f"# Forced primary (e.g. Zee Marathi HD): {forced}",
        f"# Channels: {len(final_blocks)}",
        "# Auto-refreshed by GitHub Actions",
        "",
    ]
    lines = header[:]
    for b in final_blocks:
        lines.extend(b)
        lines.append("")

    meta = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "primary": PRIMARY_URL,
        "fallback": FALLBACK_URL,
        "total": len(final_blocks),
        "from_primary": from_primary,
        "from_fallback": from_fallback,
        "forced_primary": forced,
    }
    return "\n".join(lines) + "\n", meta


def main() -> int:
    import json

    text, meta = build()
    OUT.write_text(text, encoding="utf-8")
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUT} ({meta['total']} channels: {meta['from_primary']} primary + {meta['from_fallback']} fallback)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
