"""Lightweight sitemap fetcher — replaces the Suite's cross-package
dependency on `../technical_audit/sitemap_analysis.py`.

Parses /sitemap.xml, /sitemap_index.xml, and common variants. Returns up
to N URLs without an external library.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

_UA = "Mozilla/5.0 (compatible; GrowistoSEOBot/1.0)"
_HEADERS = {"User-Agent": _UA}
_NS = re.compile(r"\{[^}]+\}")
_SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemaps/sitemap.xml",
    "/wp-sitemap.xml",
    "/sitemap1.xml",
]


def _root(domain: str) -> str:
    if "://" not in domain:
        return "https://" + domain.strip("/")
    return domain.rstrip("/")


def _strip_ns(tag: str) -> str:
    return _NS.sub("", tag)


def _parse_sitemap_xml(text: str) -> tuple[list[str], list[str]]:
    """Return (page_urls, child_sitemap_urls) from sitemap XML."""
    try:
        root = ET.fromstring(text)
    except Exception:
        return [], []

    pages: list[str] = []
    children: list[str] = []
    for el in root.iter():
        tag = _strip_ns(el.tag).lower()
        if tag == "sitemap":
            loc = el.find("{*}loc")
            if loc is not None and loc.text:
                children.append(loc.text.strip())
            else:
                # Try without namespace
                for c in el:
                    if _strip_ns(c.tag).lower() == "loc" and c.text:
                        children.append(c.text.strip())
        elif tag == "url":
            for c in el:
                if _strip_ns(c.tag).lower() == "loc" and c.text:
                    pages.append(c.text.strip())
                    break
    return pages, children


def fetch_sitemap_urls(domain: str, max_urls: int = 2000, max_child_sitemaps: int = 25) -> dict:
    """Fetch URLs from a domain's sitemap(s).

    Returns:
        {
            "available": bool,
            "total_urls": int,
            "sample_urls": list (up to max_urls),
            "child_sitemaps_tried": int,
            "error": str | None
        }
    """
    base = _root(domain)
    all_urls: list[str] = []
    child_count = 0
    last_error: str | None = None

    for candidate in _SITEMAP_CANDIDATES:
        url = base + candidate
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
            if not r.ok:
                continue
            pages, children = _parse_sitemap_xml(r.text)
            all_urls.extend(pages)
            # Recurse into child sitemaps (limited)
            for child_url in children[:max_child_sitemaps]:
                if len(all_urls) >= max_urls:
                    break
                child_count += 1
                try:
                    rc = requests.get(child_url, headers=_HEADERS, timeout=15, allow_redirects=True)
                    if rc.ok:
                        child_pages, _ = _parse_sitemap_xml(rc.text)
                        all_urls.extend(child_pages)
                except Exception as e:
                    last_error = str(e)[:80]
            if all_urls:
                break  # Found a working sitemap; stop trying candidates
        except Exception as e:
            last_error = str(e)[:80]

    # Dedupe while preserving order, then cap
    seen: set[str] = set()
    unique: list[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
        if len(unique) >= max_urls:
            break

    return {
        "available": len(unique) > 0,
        "total_urls": len(unique),
        "sample_urls": unique,
        "child_sitemaps_tried": child_count,
        "error": last_error if not unique else None,
    }
