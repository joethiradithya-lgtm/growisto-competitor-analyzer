"""Off-Page Ahrefs v3 client.

Ported from the Suite's competitor_analysis/ahrefs.py (lines 1-105) with
sequential fetches (the original used ThreadPoolExecutor for Flask SSE
responsiveness; not needed in a CLI).

Reads AHREFS_API_KEY from env. Returns {available: False, reason: ...}
if the key is missing or the API rate-limits.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from urllib.parse import urlparse

import requests

_BASE = "https://api.ahrefs.com/v3/site-explorer"


def normalize_domain(domain: str) -> str:
    """Strip scheme/www from a user-supplied domain string."""
    if "://" not in domain:
        domain = "https://" + domain
    parsed = urlparse(domain)
    host = parsed.netloc or parsed.path
    return host.replace("www.", "").strip("/")


def root_url(domain: str) -> str:
    """Return a clean https root URL."""
    return "https://" + normalize_domain(domain)


def _get(endpoint: str, params: dict, headers: dict, timeout: int = 15):
    try:
        r = requests.get(f"{_BASE}/{endpoint}", params=params, headers=headers, timeout=timeout)
        if r.status_code in (402, 429):
            return None, "limit_exhausted"
        if not r.ok:
            return None, f"api_error_{r.status_code}"
        return r.json(), None
    except Exception as e:
        return None, str(e)[:60]


def fetch_off_page(domain: str) -> dict:
    """Fetch off-page metrics for one domain.

    Returns a dict:
        available: bool
        domain: normalized form
        dr: domain rating 0-100
        backlinks_now / backlinks_90d / backlinks_delta
        refdomains_now / refdomains_90d / refdomains_delta
        organic_traffic: estimated monthly visits
        top_anchors: list of up to 5 anchor texts

    If the API key is missing or the API errors, returns:
        {"available": False, "reason": "no_key" | "limit_exhausted" | <error>}
    """
    api_key = os.environ.get("AHREFS_API_KEY", "").strip()
    if not api_key:
        return {"available": False, "reason": "no_key"}

    clean = normalize_domain(domain)
    root = root_url(domain)
    today = date.today().strftime("%Y-%m-%d")
    ago90 = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    hdrs = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    # Sequential fetches — for one domain at a time this is fast enough
    dr_data, dr_err = _get("domain-rating", {"target": clean, "date": today}, hdrs)
    if dr_err and "limit" in str(dr_err):
        return {"available": False, "reason": "limit_exhausted"}

    bl_now, bl_err = _get("backlinks-stats", {"target": root, "date": today, "mode": "subdomains"}, hdrs)
    bl_90, _ = _get("backlinks-stats", {"target": root, "date": ago90, "mode": "subdomains"}, hdrs)
    ot_data, _ = _get("metrics", {"target": clean, "date": today}, hdrs)
    anc_data, _ = _get("anchors", {"target": root, "limit": 5, "mode": "subdomains"}, hdrs)

    if dr_err or bl_err:
        return {"available": False, "reason": dr_err or bl_err}

    dr = (dr_data or {}).get("domain_rating", {}).get("domain_rating")
    bl_n = (bl_now or {}).get("metrics", {}).get("live", 0) or 0
    rd_n = (bl_now or {}).get("metrics", {}).get("live_refdomains", 0) or 0
    bl_9 = (bl_90 or {}).get("metrics", {}).get("live", 0) or 0
    rd_9 = (bl_90 or {}).get("metrics", {}).get("live_refdomains", 0) or 0
    ot = (ot_data or {}).get("metrics", {}).get("org_traffic")
    anchors_raw = (anc_data or {}).get("anchors", [])
    top_anchors = [a.get("anchor", "") for a in anchors_raw if a.get("anchor")][:5]

    return {
        "available": True,
        "domain": clean,
        "dr": dr,
        "backlinks_now": bl_n,
        "backlinks_90d": bl_9,
        "backlinks_delta": bl_n - bl_9,
        "refdomains_now": rd_n,
        "refdomains_90d": rd_9,
        "refdomains_delta": rd_n - rd_9,
        "organic_traffic": ot,
        "top_anchors": top_anchors,
    }
