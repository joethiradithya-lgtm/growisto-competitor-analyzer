#!/usr/bin/env python3
"""CLI orchestrator for the Competitor Analyzer plugin.

Two subcommands matching the same pattern as Blog Content Review (#4):

  prepare   Fetch RAW data for all enabled sections across all domains;
            write a single prep JSON for Claude to read and classify.

  build     Take Claude's completed scorecard JSON (raw + classifications
            merged) and produce the final 6-tab Excel workbook.

The split is deliberate: Python does deterministic fetching (Ahrefs API,
PSI API, scraping, schema parsing). Claude does the subjective work
(blog category clustering, footer tag classification, homepage clarity
scoring, EEAT scoring, slug audit, GEO answer-first / LLM-citation
scoring, case-study verification).

Usage:
    # Prepare RAW data for primary + 1-3 competitors
    python3 run_analysis.py prepare \\
        --primary nike.com \\
        --competitor adidas.com \\
        --competitor puma.com \\
        --competitor newbalance.com \\
        --sections off,on,tech,hyg,geo \\
        --out .work/ca_prep.json

    # Build Excel from completed scorecard
    python3 run_analysis.py build .work/ca_scorecard.json Outputs/audit.xlsx
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from ahrefs_client import fetch_off_page  # noqa: E402
from technical_fetcher import run_technical  # noqa: E402
from sitemap_fetcher import fetch_sitemap_urls  # noqa: E402
from on_page_fetcher import run_on_page  # noqa: E402
from hygiene_fetcher import run_hygiene  # noqa: E402
from geo_fetcher import run_geo  # noqa: E402
from build_workbook import build as build_workbook  # noqa: E402


SECTION_KEYS = {"off", "on", "tech", "hyg", "geo"}


def _log(msg: str) -> None:
    print(msg, flush=True)


def cmd_prepare(args) -> int:
    domains: list[tuple[str, str]] = []  # (role, domain)
    domains.append(("primary", args.primary))
    for c in (args.competitor or []):
        domains.append(("competitor", c))
    if len(domains) < 2:
        _log("ERROR: at least 1 competitor is required (use --competitor).")
        return 1
    if len(domains) > 4:
        _log(f"ERROR: max 4 domains total (1 primary + 3 competitors), got {len(domains)}.")
        return 1

    sections_requested = set((args.sections or "off,on,tech,hyg,geo").split(","))
    invalid = sections_requested - SECTION_KEYS
    if invalid:
        _log(f"ERROR: unknown section(s) {invalid}. Valid keys: {sorted(SECTION_KEYS)}")
        return 1

    # Env-var pre-flight
    if "off" in sections_requested:
        if not os.environ.get("AHREFS_API_KEY", "").strip():
            _log("WARNING: AHREFS_API_KEY is not set — Off-Page section will return 'no_key' for every domain.")
    if "tech" in sections_requested:
        if not os.environ.get("PAGESPEED_API_KEY", "").strip():
            _log("NOTE: PAGESPEED_API_KEY not set — using the Suite's hardcoded fallback (free quota).")

    output: dict = {
        "run_date": date.today().isoformat(),
        "country": (args.country or "US").upper(),
        "sections_enabled": sorted(sections_requested),
        "domains": [],
    }

    for i, (role, domain) in enumerate(domains, 1):
        _log(f"\n[{i}/{len(domains)}] {role.upper()}: {domain}")
        domain_data: dict = {"role": role, "domain": domain}

        # Sitemap first (used by on-page + hygiene)
        sitemap_result = None
        if "on" in sections_requested or "hyg" in sections_requested:
            _log(f"  ↳ fetching sitemap...")
            sitemap_result = fetch_sitemap_urls(domain, max_urls=2000)
            _log(f"    sitemap: {sitemap_result['total_urls']} URLs found "
                 f"({'available' if sitemap_result['available'] else 'NOT available'})")
            domain_data["sitemap"] = sitemap_result

        # Off-Page (Ahrefs)
        if "off" in sections_requested:
            _log(f"  ↳ Off-Page (Ahrefs)...")
            domain_data["off_page"] = fetch_off_page(domain)
            if domain_data["off_page"].get("available"):
                _log(f"    DR: {domain_data['off_page'].get('dr')}, "
                     f"backlinks: {domain_data['off_page'].get('backlinks_now')}")
            else:
                _log(f"    Off-Page UNAVAILABLE: {domain_data['off_page'].get('reason')}")

        # On-Page (raw data — Claude classifies later)
        if "on" in sections_requested:
            _log(f"  ↳ On-Page...")
            domain_data["on_page"] = run_on_page(domain, sitemap_result)
            _log(f"    pages: {domain_data['on_page']['pages'].get('total_urls')}, "
                 f"blog posts: {domain_data['on_page']['blog'].get('post_count')}, "
                 f"footer links: {domain_data['on_page']['footer'].get('total_links', 0)}")

        # Technical (metadata + PSI)
        if "tech" in sections_requested:
            _log(f"  ↳ Technical (this includes PSI — slowest step)...")
            domain_data["technical"] = run_technical(domain)
            meta = domain_data["technical"].get("metadata", {})
            _log(f"    title: {(meta.get('title') or '')[:60]!r}")
            cwv = domain_data["technical"].get("core_web_vitals", {})
            _log(f"    mobile perf: {cwv.get('mobile', {}).get('performance_score')}, "
                 f"desktop perf: {cwv.get('desktop', {}).get('performance_score')}")

        # Hygiene (raw signals)
        if "hyg" in sections_requested:
            _log(f"  ↳ Hygiene...")
            sitemap_urls = (sitemap_result or {}).get("sample_urls", [])
            domain_data["hygiene"] = run_hygiene(domain, sitemap_urls)
            bc = domain_data["hygiene"]["breadcrumbs"]
            _log(f"    breadcrumbs: {bc.get('breadcrumbs_present')}, "
                 f"slugs: {domain_data['hygiene']['slug_hygiene'].get('slug_count')}")

        # GEO (new)
        if "geo" in sections_requested:
            _log(f"  ↳ GEO...")
            domain_data["geo"] = run_geo(domain)
            home = domain_data["geo"].get("homepage", {})
            if home.get("available"):
                _log(f"    schemas: {home.get('schemas_relevant_count')}, "
                     f"FAQ pairs: {home.get('faq_pair_count')}")

        output["domains"].append(domain_data)

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    _log(f"\nWrote prep JSON: {out_path}")
    _log("")
    _log("NEXT: Claude reads this file, does AI classifications per the SKILL.md")
    _log("workflow (blog categorisation, footer tagging, clarity scoring, EEAT, GEO),")
    _log("writes a scorecard JSON, then calls:")
    _log("    python3 run_analysis.py build <scorecard.json> <output.xlsx>")
    return 0


def cmd_build(args) -> int:
    in_path = Path(args.scorecard_json).expanduser().resolve()
    out_path = Path(args.output_xlsx).expanduser().resolve()
    if not in_path.exists():
        _log(f"ERROR: scorecard JSON not found: {in_path}")
        return 1
    scorecard = json.loads(in_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(scorecard, str(out_path))
    _log(f"Wrote {out_path}")
    return 0


def main() -> int:
    try:
        import subprocess as _sp, os as _os
        _sp.Popen(['python3', _os.path.expanduser('~/.growisto-log'), 'start',
                   '--name', _os.environ.get('GROWISTO_USER', ''),
                   '--project', _os.environ.get('GROWISTO_PROJECT', ''),
                   '--tool', 'Competitor Analyzer'],
                  stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Competitor Analyzer plugin (prepare + build).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare", help="Fetch RAW data for all domains.")
    pp.add_argument("--primary", required=True, help="Primary (client) domain.")
    pp.add_argument("--competitor", action="append",
                    help="Competitor domain. Repeat 1-3 times.")
    pp.add_argument("--sections", default="off,on,tech,hyg,geo",
                    help="Comma-separated section keys to run. Default: all 5. "
                         "Keys: off, on, tech, hyg, geo")
    pp.add_argument("--country", default="US",
                    help="2-letter country code (used by future GEO SearchAPI lookups). Default: US.")
    pp.add_argument("--out", required=True, help="Output path for the prep JSON.")

    bp = sub.add_parser("build", help="Build Excel from Claude's completed scorecard.")
    bp.add_argument("scorecard_json", help="Path to the scorecard JSON.")
    bp.add_argument("output_xlsx", help="Path to write the Excel workbook.")

    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "build":
        return cmd_build(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
