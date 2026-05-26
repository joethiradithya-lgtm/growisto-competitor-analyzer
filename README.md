# Growisto Competitor Analyzer — Claude Code Plugin

Run a head-to-head competitive SEO + GEO audit for 1 primary client domain vs 1-3 competitors. Five sections, side-by-side metrics in a 6-tab Excel.

This plugin is a Claude Code conversion of the Competitor Analysis tool in the [Growisto SEO AI Suite](https://github.com/joethiradithya-lgtm/growisto-seo-ai-suite). It REDESIGNS the On-Page + Hygiene retrieval (the Suite version had retrieval bugs) and ADDS a new 5th section (GEO — Generative Engine Optimization) the Suite didn't have.

## What this plugin fixes / adds vs the Render version

| | Render web tool | This plugin |
|---|---|---|
| Sections | 4 (Off-Page, On-Page, Technical, Hygiene) | 5 (+ GEO) |
| AI classifiers | Called Anthropic API inline; needed ANTHROPIC_API_KEY per teammate | Claude (the agent) does them via SKILL.md — no extra key needed |
| On-Page retrieval | Buggy (hardcoded key lookups against AI output) | RAW data only — Claude classifies |
| Hygiene retrieval | Buggy (same pattern) | RAW signals only — Claude scores |
| Excel output | Cell-alignment / wrap-text issues | Redesigned: em-dash for None, wrap_text everywhere, frozen header |
| Trigger | Web UI form | "run competitor analysis for X" in Claude |
| Output | Excel download via browser | Excel file in `Outputs/` folder |
| API keys | AHREFS + PSI + ANTHROPIC | AHREFS + PSI |

## The 5 sections

### 1. Off-Page (Ahrefs)
Domain Rating, backlinks (now + 90d ago + delta), referring domains (now + 90d ago + delta), organic traffic, top 5 anchor texts. Requires `AHREFS_API_KEY`.

### 2. On-Page
Indexed page count (sitemap), blog post count + categories (Claude clusters from titles), top 5 blog samples, footer link counts split by tag (Claude tags: Trust / Resources / Service / Compliance / Other), homepage clarity 1-5 + verdict + strengths/weaknesses (Claude scores from above-fold text), case study count + verified URLs (Claude verifies which candidates are genuine case studies).

### 3. Technical
Title tag + length, meta description + length, OG image present, canonical URL, robots, rendering type (SSR / CSR / Mixed), mobile + desktop performance scores, LCP / CLS / TBT (mobile + desktop). Uses PageSpeed Insights API.

### 4. Hygiene
Breadcrumbs (visible + JSON-LD + nav), EEAT scores 1-5 per dimension (Claude scores from about/team/contact/awards/authors signals), slug audit (Claude flags problem slugs from sitemap sample).

### 5. GEO (NEW)
Schema markup presence + count (deterministic — script parses JSON-LD), FAQ Q&A pair count, atomic-facts signals (specific numbers, year mentions, source-phrase count, external links), answer-first score 1-5 + LLM citation readiness 1-5 + entity coverage 1-5 (Claude scores from homepage text).

## Output Excel — 6 tabs

1. **Summary** — biggest gaps where the primary trails competitors (Claude picks 5+ representative gaps; auto-fallback if Claude doesn't fill `summary.biggest_gaps`)
2. **Off-Page** — rows = metrics, columns = domains (primary first, then competitors)
3. **On-Page** — same layout
4. **Technical** — same
5. **Hygiene** — same
6. **GEO** — same

Every cell uses defensive value handling — None/empty → em-dash (`"—"`) so nothing is ever truly blank.

## Prerequisite — env vars

### AHREFS_API_KEY (required for Off-Page)
Growisto has a subscription. Set in your shell:
```bash
export AHREFS_API_KEY='your_key_here'
```
Add to `~/.zshrc` to persist. Verify with:
```bash
echo "${AHREFS_API_KEY:-NOT-SET}"
```

### PAGESPEED_API_KEY (optional)
Free tier from Google. Fallback hardcoded in the script if unset. Set if you hit quota limits:
```bash
export PAGESPEED_API_KEY='your_key_here'
```

## Install

### Option A — From this GitHub repo
```bash
claude plugins install growisto-competitor-analyzer \
  --git https://github.com/joethiradithya-lgtm/growisto-competitor-analyzer
```

### Option B — Org-wide (after pilot phase)
```bash
claude plugins install growisto-competitor-analyzer --marketplace growisto-seo
```

## Use

In Claude Code, just say:
> run competitor analysis for livguard.com vs exide.in and amaron.com

Claude will:
1. Confirm primary + competitors (asks if missing)
2. Verify AHREFS_API_KEY (warns if missing; falls back gracefully for Off-Page)
3. Run `scripts/run_analysis.py prepare ...` — fetches RAW data for all domains across all 5 sections
4. Read the prep JSON + do the AI classifications (blog categories, footer tags, clarity, EEAT, slug audit, GEO scores) for each domain
5. Write the merged scorecard JSON
6. Run `scripts/run_analysis.py build ...` — produces the 6-tab Excel
7. Report top 3 biggest gaps + single highest-leverage opportunity + path to the Excel

## Requirements

Python 3.9+ with:
- `requests>=2.31.0`
- `beautifulsoup4>=4.12.0`
- `lxml>=5.0.0`
- `openpyxl>=3.1.0`

Install via:
```bash
pip install -r requirements.txt
```

## CLI usage (without Claude)

You can run the two halves manually:

```bash
# Step 1: prepare (fetch raw data — Claude not needed)
python3 scripts/run_analysis.py prepare \
    --primary livguard.com \
    --competitor exide.in \
    --competitor amaron.com \
    --sections off,on,tech,hyg,geo \
    --country IN \
    --out Outputs/ca_prep.json

# (Read Outputs/ca_prep.json + hand-write a scorecard.json with classifications)

# Step 2: build Excel from scorecard
python3 scripts/run_analysis.py build Outputs/ca_scorecard.json Outputs/audit.xlsx
```

In practice, you let Claude write the scorecard between the two steps — that's the whole point.

## Section toggles

The `--sections` flag controls which sections to run. Comma-separated keys:
- `off` — Off-Page (Ahrefs) — ~5-10s per domain
- `on` — On-Page (sitemap + blog + footer + homepage + case studies) — ~10-30s per domain depending on site size
- `tech` — Technical (metadata + PSI) — ~30s per domain (PSI is the slowest)
- `hyg` — Hygiene (breadcrumbs + EEAT signals + slug listing) — ~5-15s per domain
- `geo` — GEO (schema detection + homepage signals) — ~2-5s per domain

Total runtime for 4 domains × 5 sections ≈ 3-12 min depending on the domains.

## Architectural note

This plugin uses the same pattern as the Blog Content Review plugin (#4): **Python is the data fetcher; Claude is the analyst.** All AI classifications (clarity scoring, EEAT scoring, footer tagging, GEO scoring, slug auditing, case study verification) happen in the SKILL.md workflow — Claude reads the raw data and applies its reasoning. The Python scripts contain ZERO Anthropic API calls.

Benefits:
- No `ANTHROPIC_API_KEY` requirement for teammates
- Claude has more context (sees the full page text the script just fetched)
- Easy to tune classification criteria — just edit the SKILL.md, no script changes

## Related

This is **plugin 6 of our 7 in-scope plugins** being converted from the Growisto SEO AI Suite.

| # | Plugin | Status |
|---|---|---|
| 1 | growisto-keyword-classifier | ✅ shipped |
| 2 | growisto-internal-linking | ✅ shipped |
| 3 | growisto-ai-citation-scraper | ✅ shipped |
| 4 | growisto-blog-content-review | ✅ shipped |
| 5 | growisto-schema-audit | ✅ shipped |
| 6 | growisto-competitor-analyzer | ⬅ this one |
| — | LinkSift | 🔀 transferred to teammate |

(Tech Audit and Page-Level Audit plugins are being built by other Growisto teammates and are not part of this conversion.)
