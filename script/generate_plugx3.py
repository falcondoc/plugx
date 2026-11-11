#!/usr/bin/env python3
"""
plugx3 — hybrid failover playlist

Primary: falcondoc plugx2 (mirror of allinonereborn jtv33 — proxy keys)
Fallback: Geo jiotv_cf
Zee overlay: premiumplugx.me/vzy + pastyx (CloudFront static clearkey)
  - Zee family NEVER from Jio sources
  - Dual Zee mirrors so keys stay fresh when one lags

Auto-refreshed by GitHub Actions every 4h.
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.request
from pathlib import Path

PRIMARY_URL = "https://raw.githubusercontent.com/falcondoc/plugx/main/plugx2.m3u"
FALLBACK_URL = "https://raw.githubusercontent.com/qwerty180506/Geo/main/jiotv_cf.m3u"
ZEE_URLS = [
    "https://premiumplugx.me/vzy/playlist.php",
    "https://pastyx.pages.dev/api/paste/vzy-playlist-m3u/raw",
]

_cwd = Path.cwd()
ROOT = _cwd if (_cwd / "script").is_dir() else Path(__file__).resolve().parent.parent
OUT = ROOT / "plugx3.m3u"
META = ROOT / ".last_check_plugx3"


def http_get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower().strip())


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
        if "license_key=" not in joined and ".mpd" not in url and ".m3u8" not in url:
            continue
        out.append({"name": name or f"Channel {cid}", "norm": norm_name(name) if name else norm_name(cid), "id": cid, "block": block})
    return out


def is_zee_family(norm: str, name: str) -> bool:
    n = norm
    nm = (name or "").strip().lower()
    if "jazeera" in n or n.startswith("aljazeera"):
        return False
    if "tehzeeb" in n or "tehzeeb" in nm:
        return False
    if n.startswith("zee") or nm.startswith("zee") or nm.startswith("zee "):
        return True
    if "zee" in n and any(x in n for x in ("anmol", "cinema", "tv", "marathi", "bangla", "tamil", "talkies", "action", "classic", "bollywood", "news", "zing", "zest", "yuva", "power", "sarthak", "thirai", "cinemalu", "keralam", "kannada", "punjabi", "biskope")):
        return True
    return False


def load_zee_overlay():
    by = {}
    sources_ok = []
    for url in ZEE_URLS:
        try:
            chs = parse_m3u_blocks(http_get(url))
            if not chs:
                print(f"  zee empty: {url}")
                continue
            sources_ok.append(url)
            for c in chs:
                if c["norm"]:
                    by[c["norm"]] = c
            print(f"  zee ok: {url} ({len(chs)} ch)")
        except Exception as e:
            print(f"  zee fail: {url} -> {e}")
    return by, sources_ok


def match_zee(norm: str, zee_by: dict):
    if norm in zee_by:
        return zee_by[norm]
    base_n = norm.replace("hd", "")
    for kn, vc in zee_by.items():
        if base_n == kn.replace("hd", ""):
            return vc
    candidates = []
    for kn, vc in zee_by.items():
        if base_n in kn.replace("hd", "") or kn.replace("hd", "") in base_n:
            if abs(len(base_n) - len(kn.replace("hd", ""))) <= 6:
                candidates.append((abs(len(base_n) - len(kn.replace("hd", ""))), vc))
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    return None


def build():
    print(f"Fetching primary: {PRIMARY_URL}")
    primary = parse_m3u_blocks(http_get(PRIMARY_URL))
    print(f"  primary: {len(primary)}")

    print(f"Fetching fallback: {FALLBACK_URL}")
    try:
        fallback = parse_m3u_blocks(http_get(FALLBACK_URL))
        print(f"  fallback: {len(fallback)}")
    except Exception as e:
        print(f"  fallback failed: {e}")
        fallback = []

    print("Fetching Zee overlays...")
    by_zee, zee_sources = load_zee_overlay()
    print(f"  zee unique norms: {len(by_zee)}")

    by_primary = {c["norm"]: c for c in primary if c["norm"]}
    by_fallback = {c["norm"]: c for c in fallback if c["norm"]}

    ordered, seen = [], set()
    for c in primary:
        k = c["norm"]
        if k and k not in seen:
            ordered.append(k)
            seen.add(k)
    for c in fallback:
        k = c["norm"]
        if k and k not in seen:
            ordered.append(k)
            seen.add(k)

    final = []
    from_primary = from_fallback = from_zee = 0
    zee_dropped = []

    for k in ordered:
        ch_p = by_primary.get(k)
        ch_f = by_fallback.get(k)
        name = (ch_p or ch_f or {}).get("name") or k

        sample = "\n".join((ch_p or ch_f or {}).get("block") or [])
        path_zee = bool(re.search(r"Zee[A-Za-z]|/Zee", sample)) and "jazeera" not in sample.lower() and "tehzeeb" not in sample.lower()
        if is_zee_family(k, name) or path_zee:
            z = match_zee(k, by_zee)
            if not z and path_zee:
                for alias in ("zeeanmol", "zeezing", "zee anmol", "zing"):
                    z = match_zee(norm_name(alias), by_zee) or z
                if "anmol" in sample.lower() and "cinema" not in sample.lower():
                    z = match_zee("zeeanmol", by_zee) or z
                if "zing" in sample.lower():
                    z = match_zee("zeezing", by_zee) or match_zee("zing", by_zee) or z
            if z:
                final.append(z["block"])
                from_zee += 1
            else:
                zee_dropped.append(name)
            continue

        if ch_p:
            final.append(ch_p["block"])
            from_primary += 1
        elif ch_f:
            final.append(ch_f["block"])
            from_fallback += 1

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        "#EXTM3U",
        f"#DATE:- {now}",
        "# plugx3 hybrid + Zee from vzy/pastyx only (no Jio Zee)",
        f"# Primary plugx2: {from_primary}",
        f"# Fallback Geo: {from_fallback}",
        f"# Zee overlay: {from_zee}",
        f"# Channels: {len(final)}",
        "# Auto-refreshed by GitHub Actions",
        "",
    ]
    lines = header[:]
    for b in final:
        lines.extend(b)
        lines.append("")

    meta = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "primary": PRIMARY_URL,
        "fallback": FALLBACK_URL,
        "zee_sources": zee_sources,
        "total": len(final),
        "from_primary": from_primary,
        "from_fallback": from_fallback,
        "from_zee": from_zee,
        "zee_dropped": zee_dropped[:40],
    }
    print(f"zee overlay: {from_zee}, dropped: {len(zee_dropped)}")
    return "\n".join(lines) + "\n", meta


def main() -> int:
    import json
    text, meta = build()
    OUT.write_text(text, encoding="utf-8")
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({meta['total']} channels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
