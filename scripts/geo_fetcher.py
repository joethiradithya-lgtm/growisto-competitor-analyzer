"""GEO (Generative Engine Optimization) section — NEW v0.1.0 baseline.

This section did NOT exist in the Suite. Joethir wanted a 5th category
covering how well each domain is set up to be cited by AI engines
(ChatGPT, Perplexity, Gemini, Google AI Overview).

The Python side gathers RAW signals. Claude does the scoring in the
SKILL.md workflow:
  - Answer-first score (does homepage lead with direct answers?)
  - LLM Citation Readiness (atomic facts, source attributions)
  - Entity coverage depth (named entities mentioned)
  - Schema markup detection (deterministic — script does this)

This is the easiest section to iterate on since there's no Suite
baseline to maintain parity with. If Joethir wants different GEO
parameters after seeing v0.1.0 in action, we revise here without
breaking anything else.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

_UA = "Mozilla/5.0 (compatible; GrowistoSEOBot/1.0)"
_HEADERS = {"User-Agent": _UA}

_GEO_RELEVANT_SCHEMAS = (
    "Article", "BlogPosting", "TechArticle", "NewsArticle",
    "Organization", "WebSite", "WebPage", "AboutPage",
    "FAQPage", "Question", "Answer",
    "BreadcrumbList",
    "HowTo", "HowToStep",
    "Product", "Offer",
    "Review", "AggregateRating",
)


def _root_url(domain: str) -> str:
    if "://" not in domain:
        return "https://" + domain.strip("/")
    return domain.rstrip("/")


def _detect_schemas(soup: BeautifulSoup) -> dict:
    """Parse JSON-LD blocks + return which GEO-relevant types are present."""
    found: set[str] = set()
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for d in items:
            if not isinstance(d, dict):
                continue
            t = d.get("@type")
            if isinstance(t, str):
                if t in _GEO_RELEVANT_SCHEMAS:
                    found.add(t)
            elif isinstance(t, list):
                for typ in t:
                    if isinstance(typ, str) and typ in _GEO_RELEVANT_SCHEMAS:
                        found.add(typ)
            for g in d.get("@graph", []) or []:
                if isinstance(g, dict):
                    gt = g.get("@type")
                    if isinstance(gt, str) and gt in _GEO_RELEVANT_SCHEMAS:
                        found.add(gt)
                    elif isinstance(gt, list):
                        for typ in gt:
                            if isinstance(typ, str) and typ in _GEO_RELEVANT_SCHEMAS:
                                found.add(typ)
    return {s: True for s in found}


def _count_faq_pairs(soup: BeautifulSoup) -> int:
    """Count question-style headings (h2/h3/h4 ending in `?`) — used to
    estimate FAQ structure (whether or not FAQPage schema is present)."""
    count = 0
    for tag in soup.find_all(["h2", "h3", "h4"]):
        text = tag.get_text(" ", strip=True)
        if text.endswith("?") and 1 <= len(text.split()) <= 15:
            count += 1
    return count


def _atomic_facts_signals(soup: BeautifulSoup) -> dict:
    """Heuristic signals for 'is this content easy to cite?'."""
    body = soup.get_text(" ", strip=True)

    # Numbers + specific data points (LLMs cite specific numbers more often than vague claims)
    number_count = len(re.findall(r"\b\d[\d,.]*(?:%|x|×|kg|km|m|cm|mm|GB|MB|MHz|GHz)?\b", body))

    # Year mentions (recency signals)
    year_count = len(re.findall(r"\b(19|20)\d{2}\b", body))

    # Source-like phrases
    source_phrases = ("according to", "source:", "via ", "as reported by", "per ", "data from")
    source_count = sum(body.lower().count(p) for p in source_phrases)

    # External link count (often used to source claims)
    external_link_count = 0
    for a in soup.find_all("a", href=True)[:500]:
        href = a["href"]
        if href.startswith("http"):
            external_link_count += 1

    return {
        "specific_numbers_count": number_count,
        "year_mentions_count": year_count,
        "source_phrase_count": source_count,
        "external_links_count": external_link_count,
    }


def fetch_homepage_geo_signals(domain: str) -> dict:
    """Collect GEO-relevant signals from a domain's homepage.

    Returns RAW data Claude reads in SKILL.md to score:
      - Answer-first (1-5): does the page lead with a direct answer / value prop?
      - LLM Citation Readiness (1-5): atomic facts, source attributions, structure?
      - Entity coverage (1-5): named entities mentioned (brands, places, products, people)?

    Output shape:
        {
            "available": bool,
            "schemas_present": dict {Type: True, ...} for GEO-relevant types,
            "schemas_relevant_count": int,
            "faq_pair_count": int (question-style headings),
            "first_paragraph": str (up to 800 chars — for answer-first scoring),
            "body_sample": str (up to 3000 chars — for entity / depth scoring),
            "atomic_facts_signals": {specific_numbers_count, year_mentions_count, source_phrase_count, external_links_count},
            "headings_count": dict
        }
    """
    url = _root_url(domain)
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20, allow_redirects=True)
        soup = BeautifulSoup(r.text, "lxml")
    except Exception as e:
        return {"available": False, "reason": str(e)[:80]}

    # First substantive paragraph (for answer-first assessment)
    first_para = ""
    for tag in soup.find_all(["p", "div", "section"]):
        text = tag.get_text(" ", strip=True)
        if len(text) > 80:
            first_para = text[:800]
            break

    body_sample = soup.get_text(" ", strip=True)[:3000]

    headings = {
        "h1": len(soup.find_all("h1")),
        "h2": len(soup.find_all("h2")),
        "h3": len(soup.find_all("h3")),
    }

    schemas_present = _detect_schemas(soup)
    return {
        "available": True,
        "schemas_present": schemas_present,
        "schemas_relevant_count": len(schemas_present),
        "faq_pair_count": _count_faq_pairs(soup),
        "first_paragraph": first_para,
        "body_sample": body_sample,
        "atomic_facts_signals": _atomic_facts_signals(soup),
        "headings_count": headings,
    }


def run_geo(domain: str) -> dict:
    """Run all GEO signal collection for one domain.

    v0.1.0 covers homepage only. If Joethir wants per-top-page sampling
    in the future (e.g. fetch the top 3 ranking pages and aggregate their
    signals), this is the function to extend.

    Output shape:
        {
            "homepage": {available, schemas_present, ...} from fetch_homepage_geo_signals
        }
    """
    return {
        "homepage": fetch_homepage_geo_signals(domain),
    }
