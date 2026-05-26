"""Hygiene section — REDESIGNED port from Suite's competitor_analysis/hygiene.py.

Key changes vs the Suite version:

1. **No AI classifier calls inside the script.** The Suite imported
   `audit_url_slugs`, `score_eeat`, `verify_page_type` from `ai.py`
   (Anthropic API calls). Gone. This module returns RAW signals —
   Claude does the verification + EEAT scoring + slug auditing in the
   SKILL.md workflow.

2. **Defensive fetches.** Every external call wrapped in try/except.
   Always returns the same structured shape so downstream code can rely
   on keys.

3. **No threading.** Sequential is fine for one domain at a time.

4. **No `sitemap_analysis` import from `../technical_audit/`.** Uses our
   own sitemap_fetcher.py results, which the orchestrator passes in.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_UA = "Mozilla/5.0 (compatible; GrowistoSEOBot/1.0)"
_HEADERS = {"User-Agent": _UA}


def _root_url(domain: str) -> str:
    if "://" not in domain:
        return "https://" + domain.strip("/")
    return domain.rstrip("/")


def _clean_domain(domain: str) -> str:
    if "://" not in domain:
        domain = "https://" + domain
    return urlparse(domain).netloc.replace("www.", "").strip("/")


# ── Breadcrumbs ──────────────────────────────────────────────────────

def check_breadcrumbs(domain: str, sitemap_urls: list[str] | None = None) -> dict:
    """Detect breadcrumbs on up to 5 deep internal pages.

    Output shape:
        {
            "breadcrumbs_present": bool,
            "breadcrumbs_jsonld": bool,
            "breadcrumbs_nav": bool,
            "found_on_urls": list of URLs where breadcrumbs were detected,
            "checked_urls": list of URLs we actually fetched
        }
    """
    candidates: list[str] = []
    if sitemap_urls:
        deep = [
            u for u in sitemap_urls
            if urlparse(u).path.strip("/").count("/") >= 1
            and not any(x in u.lower() for x in ["sitemap", ".xml", ".pdf"])
        ]
        candidates = deep[:5]

    if not candidates:
        root = _root_url(domain)
        candidates = [f"{root}/blog", f"{root}/about", f"{root}/products"]

    checked: list[str] = []
    found_on: list[str] = []
    saw_jsonld = False
    saw_nav = False

    for url in candidates:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
            soup = BeautifulSoup(r.text, "lxml")
            checked.append(url)

            has_jsonld = False
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    items = data if isinstance(data, list) else [data]
                    for d in items:
                        if not isinstance(d, dict):
                            continue
                        if "BreadcrumbList" in str(d.get("@type", "")):
                            has_jsonld = True
                            break
                        for g in d.get("@graph", []) or []:
                            if isinstance(g, dict) and "BreadcrumbList" in str(g.get("@type", "")):
                                has_jsonld = True
                                break
                    if has_jsonld:
                        break
                except Exception:
                    pass

            has_nav = bool(
                soup.find("nav", attrs={"aria-label": re.compile("breadcrumb", re.I)})
                or soup.find(attrs={"class": re.compile("breadcrumb", re.I)})
                or soup.find(attrs={"id": re.compile("breadcrumb", re.I)})
                or soup.find(attrs={"itemtype": re.compile("BreadcrumbList", re.I)})
            )

            if has_jsonld:
                saw_jsonld = True
            if has_nav:
                saw_nav = True
            if has_jsonld or has_nav:
                found_on.append(url)
        except Exception:
            pass

    return {
        "breadcrumbs_present": bool(found_on),
        "breadcrumbs_jsonld": saw_jsonld,
        "breadcrumbs_nav": saw_nav,
        "found_on_urls": found_on[:3],
        "checked_urls": checked,
    }


# ── EEAT page finders ────────────────────────────────────────────────

_PAGE_PATTERNS = {
    "about":   re.compile(r"/(about|about-us|who-we-are|our-story|our-company|company|mission)/?$", re.I),
    "team":    re.compile(r"/(team|our-team|leadership|management|people|founders|staff)/?$", re.I),
    "contact": re.compile(r"/(contact|contact-us|get-in-touch|reach-us|enquiry|support)/?$", re.I),
    "awards":  re.compile(r"/(awards|recognition|achievements|press|news-and-awards)/?$", re.I),
}
_PAGE_SLUGS = {
    "about":   ["/about", "/about-us", "/who-we-are", "/our-story", "/our-company", "/company"],
    "team":    ["/team", "/our-team", "/leadership", "/management", "/people", "/founders"],
    "contact": ["/contact", "/contact-us", "/get-in-touch", "/reach-us", "/enquiry"],
    "awards":  ["/awards", "/recognition", "/achievements", "/press"],
}


def _find_page_raw(domain: str, page_type: str, sitemap_urls: list[str]) -> dict:
    """Locate a candidate page of the given type. Returns RAW data; Claude verifies.

    Output shape:
        {
            "page_type": str,
            "candidate_url": str | None,
            "title": str,
            "body_sample": str (up to 1000 chars for Claude to read)
        }
    """
    root = _root_url(domain)
    pattern = _PAGE_PATTERNS[page_type]

    # Sitemap-based candidates
    candidates = [u for u in (sitemap_urls or []) if pattern.search(u)]

    # Slug-based fallback
    if not candidates:
        for slug in _PAGE_SLUGS[page_type]:
            try:
                r = requests.head(root + slug, headers=_HEADERS, timeout=8, allow_redirects=True)
                if r.status_code == 200:
                    candidates.append(r.url)
                    if pattern.search(r.url):
                        break
            except Exception:
                pass

    if not candidates:
        return {
            "page_type": page_type,
            "candidate_url": None,
            "title": "",
            "body_sample": "",
        }

    top = candidates[0]
    try:
        r = requests.get(top, headers=_HEADERS, timeout=15, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")
        title_el = soup.find("title")
        title = title_el.get_text(" ", strip=True)[:120] if title_el else ""
        body = soup.get_text(" ", strip=True)[:1000]
    except Exception:
        title = ""
        body = ""

    return {
        "page_type": page_type,
        "candidate_url": top,
        "title": title,
        "body_sample": body,
    }


def find_authors_raw(domain: str, sitemap_urls: list[str]) -> dict:
    """Detect author-related signals. Returns RAW data; Claude assesses authority.

    Output shape:
        {
            "author_urls_sample": list (up to 5),
            "bylines_sample": list (up to 5),
            "author_count_estimate": int,
            "has_any_author_signals": bool
        }
    """
    root = _root_url(domain)
    author_urls: list[str] = []
    bylines: list[str] = []

    if sitemap_urls:
        author_urls = [u for u in sitemap_urls if re.search(r"/author[s]?/", u, re.I)]

    try:
        r = requests.get(root + "/blog", headers=_HEADERS, timeout=15, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")

        for a in soup.find_all("a", href=True):
            if re.search(r"/author[s]?/", a["href"], re.I):
                author_urls.append(urljoin(root, a["href"]))

        for a in soup.find_all("a", attrs={"rel": "author"}):
            t = a.get_text(" ", strip=True)
            if t:
                bylines.append(t)

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for d in items:
                    if not isinstance(d, dict):
                        continue
                    sources = [d.get("author")]
                    for g in d.get("@graph", []) or []:
                        if isinstance(g, dict):
                            sources.append(g.get("author"))
                    for src in sources:
                        if isinstance(src, dict) and src.get("name"):
                            bylines.append(src["name"])
                        elif isinstance(src, list):
                            for x in src:
                                if isinstance(x, dict) and x.get("name"):
                                    bylines.append(x["name"])
            except Exception:
                pass

        for el in soup.find_all(attrs={"class": re.compile(r"(byline|author-name|post-author)", re.I)}):
            t = el.get_text(" ", strip=True)
            if t and len(t) < 80:
                bylines.append(t)
        for el in soup.find_all(attrs={"itemprop": "author"}):
            t = el.get_text(" ", strip=True)
            if t:
                bylines.append(t)
    except Exception:
        pass

    uniq_urls = list(dict.fromkeys(author_urls))[:20]
    uniq_bylines = list(dict.fromkeys(bylines))[:20]
    has_any = bool(uniq_urls) or bool(uniq_bylines)

    return {
        "author_urls_sample": uniq_urls[:5],
        "bylines_sample": uniq_bylines[:5],
        "author_count_estimate": min(max(len(uniq_urls), len(uniq_bylines)), 20),
        "has_any_author_signals": has_any,
    }


# ── EEAT aggregator (RAW signals only) ───────────────────────────────

def assess_eeat_signals(domain: str, sitemap_urls: list[str] | None = None) -> dict:
    """Collect EEAT-related RAW signals. Claude scores 1-5 per dimension in SKILL.md.

    Output shape:
        {
            "about_page":   {page_type, candidate_url, title, body_sample},
            "team_page":    {...},
            "contact_page": {...},
            "awards_page":  {...},
            "authors":      {author_urls_sample, bylines_sample, author_count_estimate, has_any_author_signals}
        }
    """
    sitemap_urls = sitemap_urls or []
    about = _find_page_raw(domain, "about", sitemap_urls)
    team = _find_page_raw(domain, "team", sitemap_urls)
    contact = _find_page_raw(domain, "contact", sitemap_urls)
    awards = _find_page_raw(domain, "awards", sitemap_urls)
    authors = find_authors_raw(domain, sitemap_urls)

    return {
        "about_page": about,
        "team_page": team,
        "contact_page": contact,
        "awards_page": awards,
        "authors": authors,
    }


# ── Slug listing (no scoring — Claude audits in SKILL.md) ────────────

def list_url_slugs(sitemap_urls: list[str] | None = None, sample_size: int = 40) -> dict:
    """List URL slugs from the sitemap. Claude audits hygiene in SKILL.md.

    Output shape:
        {
            "available": bool,
            "slug_count": int,
            "slugs_sample": list of slug strings (last path segment of each URL)
        }
    """
    urls = sitemap_urls or []
    if not urls:
        return {"available": False, "slug_count": 0, "slugs_sample": []}

    slugs: list[str] = []
    for u in urls[:sample_size]:
        path = urlparse(u).path.strip("/")
        if path:
            slugs.append(path.split("/")[-1] or path)

    return {
        "available": bool(slugs),
        "slug_count": len(slugs),
        "slugs_sample": slugs,
    }


# ── Main entry point ─────────────────────────────────────────────────

def run_hygiene(domain: str, sitemap_urls: list[str] | None = None) -> dict:
    """Aggregate all hygiene RAW signals for one domain. Sequential.

    Output shape:
        {
            "breadcrumbs":  {breadcrumbs_present, breadcrumbs_jsonld, ...},
            "eeat_signals": {about_page, team_page, contact_page, awards_page, authors},
            "slug_hygiene": {available, slug_count, slugs_sample}
        }
    """
    sitemap_urls = sitemap_urls or []
    breadcrumbs = check_breadcrumbs(domain, sitemap_urls)
    eeat_signals = assess_eeat_signals(domain, sitemap_urls)
    slugs = list_url_slugs(sitemap_urls)

    return {
        "breadcrumbs": breadcrumbs,
        "eeat_signals": eeat_signals,
        "slug_hygiene": slugs,
    }
