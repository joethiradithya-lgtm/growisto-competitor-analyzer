"""Technical SEO section.

Ported from the Suite's competitor_analysis/technical.py (lines 1-176)
with sequential fetches + PSI logic moved to psi_client.py.

Returns metadata (title, meta, OG, canonical, robots), rendering type
detection (SSR / CSR / Mixed), and Core Web Vitals (mobile + desktop).
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from psi_client import fetch_core_web_vitals

_UA = "Mozilla/5.0 (compatible; GrowistoSEOBot/1.0)"
_HEADERS = {"User-Agent": _UA}


def _root_url(domain: str) -> str:
    if "://" not in domain:
        return "https://" + domain.strip("/")
    return domain.rstrip("/")


def fetch_metadata(domain: str) -> dict:
    """Fetch homepage and extract title, meta-desc, OG tags, canonical, robots."""
    url = _root_url(domain)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")

        title_el = soup.find("title")
        title = title_el.get_text("", strip=True) if title_el else None

        desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        description = desc_tag.get("content", "").strip() if desc_tag else None

        og_title = (soup.find("meta", property="og:title") or {}).get("content")
        og_desc = (soup.find("meta", property="og:description") or {}).get("content")
        og_image = (soup.find("meta", property="og:image") or {}).get("content")

        canonical_tag = soup.find("link", rel="canonical")
        canonical = canonical_tag.get("href") if canonical_tag else None

        robots_tag = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
        robots = robots_tag.get("content") if robots_tag else None

        return {
            "title": title,
            "title_len": len(title) if title else 0,
            "description": description,
            "desc_len": len(description) if description else 0,
            "og_title": og_title,
            "og_desc": og_desc,
            "og_image": bool(og_image),
            "canonical": canonical,
            "robots": robots,
            "final_url": r.url,
            "status_code": r.status_code,
        }
    except Exception as e:
        return {"error": str(e)[:80]}


def check_ssr(domain: str) -> dict:
    """Detect SSR/CSR/Mixed by scanning static HTML for SPA framework markers."""
    url = _root_url(domain)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        html = r.text
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        return {"rendering_type": "Unknown", "reason": str(e)[:60]}

    text_tokens = len(soup.get_text(" ", strip=True).split())
    has_next_data = "__NEXT_DATA__" in html
    has_nuxt_data = "__NUXT__" in html or "window.__NUXT__" in html
    has_vue_ssr = 'data-server-rendered="true"' in html
    has_react_root = bool(soup.find(id=re.compile(r"^(root|app|__next)$")))
    react_root_empty = False
    if has_react_root:
        root_el = soup.find(id=re.compile(r"^(root|app|__next)$"))
        react_root_empty = len(root_el.get_text(strip=True)) < 50

    if has_vue_ssr or has_next_data or has_nuxt_data:
        rendering_type = "SSR" if text_tokens > 200 else "Mixed"
    elif react_root_empty and text_tokens < 100:
        rendering_type = "CSR"
    elif text_tokens > 200:
        rendering_type = "SSR"
    else:
        rendering_type = "Mixed"

    return {
        "rendering_type": rendering_type,
        "static_tokens": text_tokens,
        "spa_framework": (
            "Next.js" if has_next_data else
            "Nuxt" if has_nuxt_data else
            "Vue-SSR" if has_vue_ssr else
            "React" if has_react_root else None
        ),
    }


def run_technical(domain: str) -> dict:
    """Aggregate all technical checks for one domain. Sequential."""
    meta = fetch_metadata(domain)
    rendering = check_ssr(domain)
    # PSI runs last because it's the slowest (~10-30s per strategy)
    cwv = fetch_core_web_vitals(_root_url(domain))

    return {
        "metadata": meta,
        "core_web_vitals": cwv,
        "rendering": rendering,
    }
