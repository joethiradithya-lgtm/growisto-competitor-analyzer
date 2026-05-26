"""PageSpeed Insights (PSI) API client.

Extracted from the Suite's competitor_analysis/technical.py (lines 105-162).
Sequential mobile + desktop fetches (no threading needed for CLI).

Reads PAGESPEED_API_KEY from env. Falls back to the Suite's hardcoded key
if env var is missing (free quota is forgiving for occasional use).
"""
from __future__ import annotations

import os
import requests

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
# Hardcoded fallback matching the Suite. Free tier; quota-limited.
_FALLBACK_KEY = "AIzaSyCwg9Coc5_e7W-nTwIbhTwfl3-KG_sGfpc"


def _fetch_one(url: str, strategy: str, api_key: str, timeout: int = 55) -> dict:
    try:
        r = requests.get(
            PSI_ENDPOINT,
            params={"url": url, "key": api_key, "strategy": strategy},
            timeout=timeout,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)[:60]}


def _extract(data: dict) -> dict:
    """Pull the metrics we report from a PSI lighthouseResult payload."""
    if not data or "lighthouseResult" not in data:
        psi_err = (data or {}).get("error", {})
        err_msg = psi_err.get("message") if isinstance(psi_err, dict) else str(psi_err or "no lighthouseResult")
        return {
            "error": err_msg,
            "performance_score": None,
            "lcp": "", "fid": "", "cls": "", "fcp": "", "ttfb": "",
        }

    cats = data["lighthouseResult"].get("categories", {})
    auds = data["lighthouseResult"].get("audits", {})

    def _metric(key: str) -> str:
        audit = auds.get(key, {})
        dv = audit.get("displayValue") or ""
        if not dv:
            nv = audit.get("numericValue")
            if nv is not None:
                dv = f"{round(nv)} ms" if nv >= 1 else f"{nv:.0f} ms"
        return dv

    score = cats.get("performance", {}).get("score")
    return {
        "performance_score": round(score * 100) if score is not None else None,
        "lcp":  _metric("largest-contentful-paint"),
        "fid":  _metric("total-blocking-time"),  # Suite uses TBT here per JS convention
        "cls":  _metric("cumulative-layout-shift"),
        "fcp":  _metric("first-contentful-paint"),
        "ttfb": _metric("server-response-time"),
    }


def fetch_core_web_vitals(url: str) -> dict:
    """Fetch PSI metrics for both mobile + desktop strategies.

    Args:
        url: full URL to test (https://example.com/)

    Returns:
        {"mobile": {...}, "desktop": {...}} where each dict has
        performance_score, lcp, fid (TBT), cls, fcp, ttfb.
    """
    api_key = os.environ.get("PAGESPEED_API_KEY", _FALLBACK_KEY).strip() or _FALLBACK_KEY

    mobile_raw = _fetch_one(url, "mobile", api_key)
    desktop_raw = _fetch_one(url, "desktop", api_key)

    return {
        "mobile": _extract(mobile_raw),
        "desktop": _extract(desktop_raw),
    }
