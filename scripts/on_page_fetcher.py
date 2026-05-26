"""On-Page section — REDESIGNED port from Suite's competitor_analysis/onpage.py.

Key changes vs the Suite version:

1. **No AI classifier calls inside the script.** The Suite imported
   `cluster_blog_categories`, `tag_footer_links`, `rate_homepage_clarity`,
   `verify_case_studies` from `ai.py` (Anthropic API calls). Those are
   GONE here. This module returns RAW data — Claude classifies / scores
   it in the SKILL.md workflow.

2. **No hardcoded key lookups against AI output.** The Suite's Excel
   builder did `footer.tagged['Trust']` which broke when the AI returned
   slightly different keys. Now the script returns the RAW footer link
   texts; Claude tags them; the Excel builder reads the categorized
   dict from the scorecard JSON Claude wrote.

3. **Defensive sitemap parsing.** Uses our own sitemap_fetcher.py
   (no cross-package dependency on `../technical_audit/`).

4. **Always returns a structured shape** even on errors, so downstream
   code can rely on the keys being present.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_UA = "Mozilla/5.0 (compatible; GrowistoSEOBot/1.0)"
_HEADERS = {"User-Agent": _UA}

_BLOG_PATTERNS = re.compile(r"/(blog|insights|resources|articles|news|posts)/", re.I)
_CASE_STUDY_PATTERNS = re.compile(
    r"/(case.stud|portfolio|success.stor|client.stor|work|projects?)/", re.I
)


def _root_url(domain: str) -> str:
    if "://" not in domain:
        return "https://" + domain.strip("/")
    return domain.rstrip("/")


def _clean_domain(domain: str) -> str:
    if "://" not in domain:
        domain = "https://" + domain
    return urlparse(domain).netloc.replace("www.", "").strip("/")


def discover_blog_posts(domain: str, sitemap_urls: list[str]) -> list[str]:
    """Return URLs that look like blog posts. Prefers sitemap; falls back to crawling /blog."""
    if sitemap_urls:
        return [u for u in sitemap_urls if _BLOG_PATTERNS.search(u)][:40]

    root = _root_url(domain)
    try:
        r = requests.get(f"{root}/blog", headers=_HEADERS, timeout=15, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")
        links: set[str] = set()
        clean = _clean_domain(domain)
        for a in soup.find_all("a", href=True):
            href = urljoin(root, a["href"])
            if _BLOG_PATTERNS.search(href) and clean in href:
                links.add(href)
        return list(links)[:40]
    except Exception:
        return []


def fetch_blog_titles(domain: str, sitemap_urls: list[str] | None = None) -> dict:
    """Find blog posts and fetch their titles. Returns RAW titles for Claude to cluster.

    Output shape:
        {
            "post_count": int,
            "post_urls": list of up to 40 URLs,
            "post_titles": list of up to 30 titles (Claude clusters these into categories),
            "sample_urls": list of 5 (first 5 of post_urls)
        }
    """
    posts = discover_blog_posts(domain, sitemap_urls or [])
    if not posts:
        return {"post_count": 0, "post_urls": [], "post_titles": [], "sample_urls": []}

    titles: list[str] = []
    for url in posts[:30]:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
            soup = BeautifulSoup(r.text, "lxml")
            tag = soup.find("h1") or soup.find("title")
            if tag:
                titles.append(tag.get_text(" ", strip=True)[:120])
        except Exception:
            pass

    return {
        "post_count": len(posts),
        "post_urls": posts[:40],
        "post_titles": titles,
        "sample_urls": posts[:5],
    }


def fetch_footer_links(domain: str) -> dict:
    """Parse footer link texts. Returns RAW texts for Claude to tag (Trust/Resources/etc.).

    Output shape:
        {
            "available": bool,
            "total_links": int,
            "raw_links": list of link anchor texts (deduped, max 60),
            "footer_html_present": bool
        }
    """
    url = _root_url(domain)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")
        footer = soup.find("footer") or soup.find(attrs={"id": re.compile("footer", re.I)})
        if not footer:
            return {
                "available": False,
                "reason": "no_footer_found",
                "total_links": 0,
                "raw_links": [],
                "footer_html_present": False,
            }

        texts: list[str] = []
        for a in footer.find_all("a", href=True):
            t = a.get_text(" ", strip=True)
            if t and len(t) < 60:
                texts.append(t)
        texts = list(dict.fromkeys(texts))[:60]  # dedup + cap

        return {
            "available": True,
            "total_links": len(texts),
            "raw_links": texts,
            "footer_html_present": True,
        }
    except Exception as e:
        return {
            "available": False,
            "reason": str(e)[:80],
            "total_links": 0,
            "raw_links": [],
            "footer_html_present": False,
        }


def fetch_homepage_sample(domain: str) -> dict:
    """Grab visible homepage text for Claude to score clarity.

    Output shape:
        {
            "available": bool,
            "above_fold_text": str (up to 2000 chars),
            "text_chunks_count": int,
            "headings_count": dict {h1: N, h2: N, h3: N}
        }
    """
    url = _root_url(domain)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")

        chunks: list[str] = []
        for tag in soup.find_all(["h1", "h2", "p", "button", "a"], limit=40):
            txt = tag.get_text(" ", strip=True)
            if txt and len(txt) > 5:
                chunks.append(txt)
            if sum(len(c) for c in chunks) > 2000:
                break
        above_fold = " | ".join(chunks)[:2000]

        headings = {
            "h1": len(soup.find_all("h1")),
            "h2": len(soup.find_all("h2")),
            "h3": len(soup.find_all("h3")),
        }

        return {
            "available": True,
            "above_fold_text": above_fold,
            "text_chunks_count": len(chunks),
            "headings_count": headings,
        }
    except Exception as e:
        return {
            "available": False,
            "reason": str(e)[:80],
            "above_fold_text": "",
            "text_chunks_count": 0,
            "headings_count": {"h1": 0, "h2": 0, "h3": 0},
        }


def fetch_case_studies(domain: str, sitemap_urls: list[str] | None = None) -> dict:
    """Find case study URLs and their titles. Returns RAW data for Claude to verify.

    Output shape:
        {
            "candidates": list of URLs found (up to 20),
            "candidate_titles": list of titles for those URLs (parallel array),
            "total_candidates": int
        }

    Claude reads the candidates + titles and decides which are GENUINE case
    studies vs lookalikes.
    """
    root = _root_url(domain)
    clean = _clean_domain(domain)

    candidates: list[str] = []
    if sitemap_urls:
        candidates = [u for u in sitemap_urls if _CASE_STUDY_PATTERNS.search(u)][:30]

    if not candidates:
        for slug in ["/case-studies", "/portfolio", "/work", "/success-stories"]:
            try:
                r = requests.get(root + slug, headers=_HEADERS, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "lxml")
                    for a in soup.find_all("a", href=True):
                        href = urljoin(root, a["href"])
                        if clean in href and _CASE_STUDY_PATTERNS.search(href):
                            candidates.append(href)
                    if candidates:
                        break
            except Exception:
                pass

    candidates = list(dict.fromkeys(candidates))[:20]

    titles: list[str] = []
    for u in candidates[:15]:
        try:
            r = requests.get(u, headers=_HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "lxml")
            h = soup.find("h1") or soup.find("title")
            titles.append(h.get_text(" ", strip=True)[:100] if h else "")
        except Exception:
            titles.append("")

    return {
        "candidates": candidates,
        "candidate_titles": titles,
        "total_candidates": len(candidates),
    }


def run_on_page(domain: str, sitemap_result: dict | None = None) -> dict:
    """Aggregate all On-Page checks. Returns RAW data only — no AI classifications.

    Claude does these in the SKILL.md workflow:
    - cluster `post_titles` into blog categories
    - tag `raw_links` into Trust/Resources/Service/Compliance/Other
    - score `above_fold_text` for homepage clarity (1-5) + strengths/weaknesses
    - verify `candidates` are GENUINE case studies (by reading titles)

    Output shape:
        {
            "pages": {total_urls, has_sitemap, sample_urls, all_urls},
            "blog": {post_count, post_urls, post_titles, sample_urls},
            "footer": {available, total_links, raw_links, footer_html_present},
            "homepage": {available, above_fold_text, text_chunks_count, headings_count},
            "case_studies": {candidates, candidate_titles, total_candidates}
        }
    """
    sitemap_urls = (sitemap_result or {}).get("sample_urls", [])

    pages_data = {
        "total_urls": (sitemap_result or {}).get("total_urls", 0),
        "has_sitemap": (sitemap_result or {}).get("available", False),
        "sample_urls": sitemap_urls[:10],
        "all_urls": sitemap_urls,
    }

    blog_data = fetch_blog_titles(domain, sitemap_urls)
    footer_data = fetch_footer_links(domain)
    homepage_data = fetch_homepage_sample(domain)
    cs_data = fetch_case_studies(domain, sitemap_urls)

    return {
        "pages": pages_data,
        "blog": blog_data,
        "footer": footer_data,
        "homepage": homepage_data,
        "case_studies": cs_data,
    }
