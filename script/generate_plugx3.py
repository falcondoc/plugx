#!/usr/bin/env python3
"""
plugx3 — hybrid failover playlist

Primary: allinonereborn jtv33 (proxy keys + cookie on URL)
Fallback: Geo jiotv_cf
Zee overlay: premiumplugx.me/vzy (CloudFront + static clearkey) — Zee family dies on Jio tokens

Auto-refreshed by GitHub Actions.
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.request
from pathlib import Path

PRIMARY_URL = "https://allinonereborn2.online/jiotv-m3u/jtv33.m3u8"
FALLBACK_URL = "https://raw.githubusercontent.com/qwerty180506/Geo/main/jiotv_cf.m3u"
ZEE_URL = "https://premiumplugx.me/vzy/playlist.php"

_cwd = Path.cwd()
ROOT = _cwd if (_cwd / "script").is_dir() else Path(__file__).resolve().parent.parent
OUT = ROOT / "plugx3.m3u"
META = ROOT / ".last_check_plugx3"

FORCE_PRIMARY = {"zeemarathihd"}


def http_get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def norm_name(s: str) -> str:
    s = (s or "").lower().strip()
    return re.sub(r"[^a-z0-9]+", "", s)


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
        out.append(
            {
                "name": name or f"Channel {cid}",
                "norm": norm_name(name) if name else norm_name(cid),
                "id": cid,
                "block": block,
            }
        )
    return out


def is_zee_family(norm: str, name: str) -> bool:
    n = norm
    if n.startswith("aljazeera") or "jazeera" in n:
        return False
    if n.startswith("tehzeeb") or "tehzeeb" in n:
        return False
    if n.startswith("zee") or name.strip().lower().startswith("zee"):
        return True
    return False


def match_zee(norm: str, zee_by: dict):
    if norm in zee_by:
        return zee_by[norm]
    candidates = []
    for kn, vc in zee_by.items():
        if norm == kn:
            return vc
        base_n = norm.replace("hd", "")
        base_k = kn.replace("hd", "")
        if base_n == base_k:
            candidates.append(vc)
            continue
        if norm in kn or kn in norm:
            if abs(len(norm) - len(kn)) <= 4:
                candidates.append(vc)
    return candidates[0] if candidates else None


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

    print(f"Fetching Zee overlay: {ZEE_URL}")
    try:
        zee_list = parse_m3u_blocks(http_get(ZEE_URL))
        print(f"  vzy: {len(zee_list)}")
    except Exception as e:
        print(f"  vzy failed: {e}")
        zee_list = []

    by_primary = {c["norm"]: c for c in primary if c["norm"]}
    by_fallback = {c["norm"]: c for c in fallback if c["norm"]}
    by_zee = {c["norm"]: c for c in zee_list if c["norm"]}

    ordered = []
    seen = set()
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
    zee_replaced = 0
    zee_unmatched = []

    for k in ordered:
        ch_p = by_primary.get(k)
        ch_f = by_fallback.get(k)
        name = (ch_p or ch_f or {}).get("name") or k

        if is_zee_family(k, name):
            z = match_zee(k, by_zee)
            if z:
                final.append(z["block"])
                from_zee += 1
                zee_replaced += 1
                continue
            zee_unmatched.append(name)

        if k in FORCE_PRIMARY and ch_p:
            final.append(ch_p["block"])
            from_primary += 1
        elif ch_p:
            final.append(ch_p["block"])
            from_primary += 1
        elif ch_f:
            final.append(ch_f["block"])
            from_fallback += 1

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = [
        "#EXTM3U",
        f"#DATE:- {now}",
        "# plugx3 hybrid failover + Zee from premiumplugx.me/vzy",
        f"# Primary jtv33: {from_primary}",
        f"# Fallback Geo: {from_fallback}",
        f"# Zee overlay vzy: {from_zee}",
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
        "zee_overlay": ZEE_URL,
        "total": len(final),
        "from_primary": from_primary,
        "from_fallback": from_fallback,
        "from_zee": from_zee,
        "zee_replaced": zee_replaced,
        "zee_unmatched": zee_unmatched[:30],
    }
    print(f"zee replaced: {zee_replaced}, unmatched: {len(zee_unmatched)}")
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
