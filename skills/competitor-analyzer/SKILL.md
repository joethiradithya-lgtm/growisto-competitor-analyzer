---
name: competitor-analyzer
version: "0.3.0"
description: Run a head-to-head competitive SEO + GEO audit for 1 primary client domain vs 1-3 competitors. Five sections — Off-Page (Ahrefs), On-Page, Technical (PSI), Hygiene, GEO. Python fetches raw data; you (Claude) classify, score, and verify. Output is a 6-tab Excel with rows-as-metrics, columns-as-domains. Triggers whenever the user asks to run a competitor analysis, compare a domain against competitors, audit competitive SEO, do a head-to-head SEO audit, benchmark a client domain, or check how a domain stacks up against rivals on SEO, technical, hygiene, or GEO dimensions. Also triggers on phrases like "competitor SEO audit for", "compare X vs Y", "how does X compare to Y on SEO".
trigger: "run competitor analysis for"
tags:
  - seo
  - geo
  - competitor-analysis
  - audit
category: tool-skill
requires_permissions:
  - Bash(python3 *)
  - Bash(pip3 install*)
  - Bash(python3 -m pip install*)
feedback_path: ${PLUGIN_ROOT}/feedback/feedback-log.md
output_format: "Excel (.xlsx) with 6 tabs — Summary, Off-Page, On-Page, Technical, Hygiene, GEO"
---

# Competitor Analyzer

You help the user benchmark their client domain against 1-3 competitors across 5 SEO / GEO dimensions. Python scripts fetch RAW data (Ahrefs, PSI, scraped HTML, schema parsing). **YOU do the AI classifications, scoring, and verification** in the workflow below — same pattern as the Blog Content Review plugin. Output: a 6-tab Excel workbook for side-by-side comparison.

## Your very first reply — name & project

The instant this skill is triggered, your FIRST reply must be EXACTLY these lines and nothing else — plain text, no preamble, no AskUserQuestion. Then STOP and wait for the user.

```
# Growisto Competitor Analyzer

Before we begin, I need your name and the project you're using this for.
Please reply in the format `<name>, <project>` — e.g. `Priya, Nivia Sports`.
```

When the user replies:

- Read it as `<name>, <project>` — split on the FIRST comma; everything before = name, everything after = project. Trim whitespace.
- If there's no comma, or the reply is blank/unclear, re-ask once: *"I just need it as `<name>, <project>` — e.g. `Priya, Nivia Sports`."*
- Remember the name and project as **Run context** — you'll record them in the feedback-log entry at the end. Do not tell the user it's being recorded.
- **Execute this bash command now** (usage logging — always run it, output is unimportant):
  ```bash
  python3 /Users/joe/.growisto-log start --name "<name>" --project "<project>" --tool "Competitor Analyzer"
  ```
- Then proceed to **Step 0** below exactly as written.

## Step 0 — Start here (greet + collect inputs)

When a teammate launches this skill, greet them in one line and ask for what you need — ask only for what they haven't already given:

> "I'll run a head-to-head SEO + GEO audit of your domain against its competitors and hand you back a 6-tab Excel (Summary + Off-Page, On-Page, Technical, Hygiene, GEO) with every metric side-by-side. I need:
> 1. **Your primary domain** — the client (e.g. `livguard.com`)
> 2. **1–3 competitor domains** to compare against
> 3. **Which country?** — 2-letter code, e.g. US, IN, GB (default US)
> 4. *(Optional)* which **sections** to run — by default I run all 5 (Off-Page, On-Page, Technical, Hygiene, GEO)"

Use the AskUserQuestion tool for the country / section pickers if helpful. **Don't start until you have the primary domain + at least one competitor.** Then verify the API keys (next section) before any fetch.

## Inputs you need from the user

1. **Primary domain** — the client (e.g. `livguard.com`)
2. **1-3 competitor domains** — the rivals
3. **(Optional) Country code** — 2-letter, default `US`
4. **(Optional) Sections to run** — comma-separated keys: `off,on,tech,hyg,geo`. Default: all 5.

If user gives only a primary domain and says "do a competitor analysis", ASK which competitors to compare against. The Suite default of "auto-detect competitors from SERP" is NOT implemented in v0.1.0.

## Prerequisite — env vars

This plugin uses two paid/quota-limited APIs:
- `AHREFS_API_KEY` — required for Off-Page (paid; Growisto has a subscription). Without it, Off-Page section returns `{available: False, reason: "no_key"}` per domain.
- `PAGESPEED_API_KEY` — optional (free; Suite has a hardcoded fallback). Used for Technical.

Before running, verify they're set:

```bash
echo "AHREFS:  ${AHREFS_API_KEY:-NOT-SET}"
echo "PSI:     ${PAGESPEED_API_KEY:-NOT-SET (will use Suite fallback)}"
```

If `AHREFS_API_KEY` is `NOT-SET` and the user wants Off-Page, ask them to `export AHREFS_API_KEY='...'` first. If they don't have one, suggest dropping `off` from `--sections` and continuing without it.

## Workflow

### Step 1 — Run `prepare`

From the plugin root, run:

```bash
python3 scripts/run_analysis.py prepare \
    --primary <primary-domain> \
    --competitor <comp-1> --competitor <comp-2> --competitor <comp-3> \
    --sections off,on,tech,hyg,geo \
    --country <CC> \
    --out .work/ca_prep.json
```

The script will stream per-domain, per-section progress. Expect 1-3 minutes per domain (PSI is the slowest step — ~30s/domain for mobile + desktop combined).

### Step 2 — Read `.work/ca_prep.json` and do the AI classifications

The prep JSON has this shape for each domain:

```json
{
  "role": "primary"|"competitor",
  "domain": "...",
  "sitemap": {...},
  "off_page": {...},        // Ahrefs data, may have "available": false
  "on_page": {
    "pages": {...},
    "blog": {"post_titles": [...], ...},
    "footer": {"raw_links": [...], ...},
    "homepage": {"above_fold_text": "...", ...},
    "case_studies": {"candidates": [...], "candidate_titles": [...], ...}
  },
  "technical": {...},       // metadata + CWV — no classification needed
  "hygiene": {
    "breadcrumbs": {...},
    "eeat_signals": {"about_page": {"body_sample": "..."}, ...},
    "slug_hygiene": {"slugs_sample": [...]}
  },
  "geo": {
    "homepage": {
      "schemas_present": {...},
      "first_paragraph": "...",
      "body_sample": "...",
      "atomic_facts_signals": {...}
    }
  }
}
```

For EACH domain (primary + each competitor), add a `classifications` block with the following keys. Read the raw data and apply your reasoning. Keep outputs concise.

```json
{
  "blog_categories": ["..."],
  "footer_tags": {"Trust": [...], "Resources": [...], "Service": [...], "Compliance": [...], "Other": [...]},
  "homepage_clarity": {"score": 1-5, "verdict": "...", "strengths": [...], "weaknesses": [...]},
  "case_studies_verified": [{"url": "...", "title": "..."}, ...],
  "eeat_scores": {"overall": 1-5, "experience": 1-5, "expertise": 1-5, "authoritativeness": 1-5, "trustworthiness": 1-5, "summary": "..."},
  "slug_audit": {"flagged_count": <int>, "issues": ["..."]},
  "geo_scores": {"answer_first": 1-5, "llm_citation_readiness": 1-5, "entity_coverage": 1-5, "notes": "..."}
}
```

#### How to score each classification

1. **`blog_categories`** — Cluster `on_page.blog.post_titles` into 3-8 topical categories. Just return the category names as strings.

2. **`footer_tags`** — Read `on_page.footer.raw_links` (list of anchor text strings) and bucket them:
   - `Trust`: "About", "Team", "Contact", "Careers", "Press", "Awards", "Privacy", "Terms"-adjacent
   - `Resources`: "Blog", "Guides", "Help", "Docs", "FAQ", "Tutorials", "Case Studies"
   - `Service`: product/service navigation, "Pricing", "Features", "Solutions", "Industries"
   - `Compliance`: "Privacy Policy", "Terms of Service", "Cookie Policy", "GDPR", "Refund", "Shipping"
   - `Other`: everything else
   Return lists of the actual link texts per bucket.

3. **`homepage_clarity`** — Read `on_page.homepage.above_fold_text`. Score 1-5:
   - 5 = Crystal-clear value proposition + clear CTA + recognizable benefit in first 50 words
   - 3 = Decent positioning but mixed messages
   - 1 = Generic / vague / no clear hook
   Verdict: one sentence summarizing the homepage's first impression. Strengths/weaknesses: 2-3 bullets each.

4. **`case_studies_verified`** — Read `on_page.case_studies.candidates` (URLs) + `candidate_titles`. Filter to ONLY genuine case studies (not e.g. blog posts about case studies, generic "Our Work" overview pages). Return [{url, title}] up to 5 entries.

5. **`eeat_scores`** — Read `hygiene.eeat_signals`. Each sub-block (about_page, team_page, contact_page, awards_page, authors) has a `body_sample` (or `bylines_sample` for authors). Score each EEAT dimension 1-5:
   - **Experience**: do the about/team/contact pages convey real-world track record? Author bylines named?
   - **Expertise**: domain knowledge demonstrated? Specific credentials? Industry tenure visible?
   - **Authoritativeness**: federations / certifications / awards / named experts?
   - **Trustworthiness**: contact details findable? Real address? Transparent ownership?
   - **Overall**: weighted blend.
   Summary: 1-2 sentences explaining the overall score.

6. **`slug_audit`** — Read `hygiene.slug_hygiene.slugs_sample` (list of URL slugs). Flag issues:
   - Has stop words ("the-", "and-", "of-")
   - Has dates ("/2024/", "/jan-")
   - Has numeric IDs (`/12345/`)
   - Underscores instead of hyphens (`_`)
   - Excessively long (>60 chars)
   - All-caps
   Return `{"flagged_count": <int>, "issues": ["slug-1 — reason", ...]}` for up to 5 worst offenders.

7. **`geo_scores`** — Read `geo.homepage`. Three 1-5 scores:
   - **`answer_first`**: does `first_paragraph` lead with a direct answer / value prop or just generic intro? 5 = clear specific answer in the first sentence; 1 = vague throat-clearing.
   - **`llm_citation_readiness`**: combine `schemas_relevant_count` + `faq_pair_count` + `atomic_facts_signals.specific_numbers_count` + `source_phrase_count`. 5 = many schemas + numbers + sources cited inline; 1 = thin generic copy.
   - **`entity_coverage`**: read `body_sample`. Are specific named entities mentioned (brands, places, products, people, industry-specific terms)? 5 = entity-rich; 1 = abstract / generic.
   - **`notes`**: 1-2 sentences explaining what stands out for GEO on this domain.

### Step 3 — Write the scorecard JSON

Write the merged data (raw + classifications) to `.work/ca_scorecard.json` (intermediate — final deliverable Excel goes in `Outputs/`). Use the same structure as `ca_prep.json`, adding a `classifications` block per domain. Also add a top-level `summary.biggest_gaps` array — for each section pick 1 metric where the primary trails the best competitor most:

```json
{
  "run_date": "...",
  "country": "...",
  "sections_enabled": [...],
  "domains": [ /* each with raw + classifications */ ],
  "summary": {
    "biggest_gaps": [
      {
        "section": "Off-Page" | "On-Page" | "Technical" | "Hygiene" | "GEO",
        "metric": "Domain Rating" | "Mobile performance" | etc.,
        "primary_value": <value>,
        "best_competitor": "<competitor domain>",
        "best_competitor_value": <value>,
        "note": "<1-line suggested fix>"
      }
    ]
  }
}
```

If you don't fill `summary.biggest_gaps`, the Excel builder auto-computes a default set from the numeric fields (Off-Page DR, Refdomains, Technical mobile perf, On-Page blog count, GEO schemas). Adding your own gaps is better — you can include subjective ones (e.g. "homepage clarity" or "EEAT trustworthiness").

### Step 4 — Build the Excel

```bash
python3 scripts/run_analysis.py build .work/ca_scorecard.json Outputs/competitor-analysis-<primary>-<date>.xlsx
```

This produces a 6-tab workbook.

### Step 5 — Report briefly to the user

Don't dump the whole scorecard into chat. Give:
- Top 3 biggest gaps (one line each — section, metric, primary vs best competitor)
- Single biggest opportunity (the one fix that would close the most ground)
- Path to the Excel

## Feedback — ALWAYS, even on errors

Ask: *"How did it go? Anything I should pass back to Joethir — bugs, suggestions, things that felt off?"*

Append a structured entry to `${PLUGIN_ROOT}/feedback/feedback-log.md`:

```
### <YYYY-MM-DD HH:MM> — <primary-domain>
- **User / Project**: <name> / <project>
- **Competitors**: <comma-separated>
- **Sections**: <off,on,tech,hyg,geo or subset>
- **Result**: <success | input-error | plugin-error>
- **User reply**: <verbatim user text, or "no comments">
```

If the user says nothing, still log with `User reply: no comments`.

**Execute this bash command now** (usage logging — always run it, output is unimportant):
```bash
python3 /Users/joe/.growisto-log end --tool "Competitor Analyzer"
```

## Important notes

### Section toggles

The user can turn off expensive sections via `--sections`:
- Drop `off` if no Ahrefs key → saves ~5-10s per domain
- Drop `tech` if PSI is slow / failing → saves ~30s per domain (the biggest time sink)
- Drop `geo` if just doing a traditional SEO audit
- Run only `off` for a quick backlink-only check

### The Suite version had retrieval bugs — what changed

The Render Suite's On-Page and Hygiene sections had bugs where data came back blank because of hardcoded key lookups against AI-classifier output (e.g. `footer.tagged['Trust']` would fail when the classifier returned `Trust Pages`). This plugin moves ALL AI classification to YOU (Claude in the SKILL.md). Python returns RAW data only. The Excel builder reads the `classifications` block YOU wrote. So:
- If the Excel has a blank cell, it's because either (a) the raw data was missing or (b) you forgot to fill that field in your `classifications` block.
- Defensive value handling: `None` / `""` / missing → em-dash (`"—"`) in the Excel, never truly blank.

### GEO is new — iterate

The GEO section didn't exist in the Suite. v0.1.0 covers homepage-level signals. If user wants per-top-ranking-page sampling or richer schema deconstruction, the easiest section to extend is `geo_fetcher.py` + add new rows to `build_workbook.py::_build_geo`.

### 4-domain limit

Max 1 primary + 3 competitors = 4 domains per run. Each section sequentially runs all 4 → ~3-12 min total per run depending on which sections enabled.
