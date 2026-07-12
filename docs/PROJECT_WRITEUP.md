# OutboundOS — Project Writeup

**Author:** Swapnita Sahu  
**Date:** July 2026  
**Repository:** OutboundOS (local / portfolio project)  
**Official benchmark:** `eval-20260711-145039` · [`data/benchmark_results.json`](../data/benchmark_results.json)

---

## Executive Summary

OutboundOS is a multi-agent AI system that automates the research and drafting workflow of an outbound Sales Development Representative (SDR). Given a company name and website, the system:

1. Researches the company from live web sources
2. Scores ideal customer profile (ICP) fit **against an explicit seller profile** (who "we" are, what we sell, who we target)
3. Identifies evidence-backed pain points
4. Selects a buyer persona
5. Drafts a personalized cold email
6. Reviews the email for quality and either approves, rewrites, or triggers re-research

The project includes **OutboundBench**, a custom 100-company evaluation dataset with ground-truth labels, evidence URLs, and reference outreach — plus a full evaluation framework that measures agent performance across six metrics.

On the official n=100 benchmark run (live agents, July 2026, post seller-profile fix):

| Metric | Score |
|--------|-------|
| Research accuracy | **98%** |
| Pain point accuracy | **87%** |
| Email quality | **96%** |
| Reviewer agreement | **98%** |
| ICP accuracy | **72%** (dropped from a prior 91% baseline — on purpose, see Section 5.0) |
| Persona accuracy | **29%** (known gap) |

Average cost: **$0.0090 / company** · Average latency: **51 seconds / company**

This writeup explains what was built, why design decisions were made, how evaluation works, and what the results mean — including honest discussion of limitations. It also documents a mid-project fix (ICP/persona scoring lacked any seller context) and the honest, somewhat counterintuitive result of fixing it: one benchmark number got *worse*, on purpose, for well-understood reasons — see Section 5.0.

---

## 1. Problem Statement

Outbound sales is labor-intensive. A human SDR typically spends 15–30 minutes per account researching a company, identifying relevant pain points, choosing the right buyer persona, and drafting a personalized email. At scale, this becomes expensive, inconsistent, and hard to measure.

The core question this project addresses:

> **Can a multi-agent LLM system perform evidence-grounded outbound research and messaging at useful accuracy, with measurable quality and reasonable cost?**

Most demo-grade "AI SDR" projects skip rigorous evaluation — they show one polished example email and call it done. OutboundOS was built with evaluation as a first-class concern: a held-out benchmark dataset, per-metric scoring, run history, and reproducible baselines.

---

## 2. What Was Built

### 2.1 OutboundOS Agent Platform

A production-oriented Python application that orchestrates six specialized agents through a **LangGraph** state machine:

```
START → Research → ICP → Pain Points → Persona → Email → Reviewer
                              ↑              ↓         ↓
                              └── RESEARCH ←─┘    REWRITE → Reviewer
```

**Key design choices:**

- **Specialized agents, not one monolithic prompt.** Each stage has a focused responsibility, structured Pydantic output schema, and dedicated system prompt. This makes debugging, evaluation, and iteration tractable.
- **Reviewer loop with three decisions.** The reviewer agent can APPROVE, request REWRITE (regenerate email), or request RESEARCH (go back to web research). This mirrors how a human QA process would work.
- **Live mode vs. fallback mode.** When `OPENAI_API_KEY` is set and `BENCHMARK_MODE=false`, agents use real Firecrawl scraping, Tavily web search, and OpenAI structured outputs. Otherwise, heuristic placeholders run for CI and offline development.
- **Structured outputs everywhere.** All agent responses are validated Pydantic models via OpenAI's structured output API, reducing parsing failures and enabling type-safe downstream consumption.

### 2.2 OutboundBench Dataset

A 100-company B2B evaluation dataset built from a curated seed list (`app/dataset/seed_companies.csv`). Companies span SaaS categories: CRM, dev tools, fintech, security, marketing automation, productivity, data platforms, and more (Stripe, HubSpot, Snowflake, Datadog, Gong, etc.).

**Each record contains:**

| Field | Purpose |
|-------|---------|
| `company_name`, `website` | Target account |
| `industry`, `short_description` | Ground-truth company profile |
| `target_persona` | Natural-language buyer description |
| `pain_points` | 3–5 evidence-backed pain points (JSON array) |
| `evidence_urls` | Source URLs used to derive labels |
| `evidence_snippets` | Text excerpts from those sources |
| `reference_outreach` | Human-style reference cold email |
| `confidence_score` | Pipeline confidence (0–1) |
| `source_quality_score` | Evidence diversity/quality score |
| `needs_human_review` | Flag if automated validation failed |

**Dataset build pipeline** (`app/dataset/build_outboundbench.py`):

1. Load seed companies from CSV
2. Collect web evidence per company (Firecrawl page scrapes + Tavily search) — shared tooling with the live agents
3. LLM extraction: industry, description, persona, pain points (structured output, evidence-grounded prompts)
4. LLM outreach generation: reference cold email grounded in pain points and evidence
5. Automated validation: unsupported-claim detection, pain-point grounding checks, source quality scoring
6. Export to CSV, JSONL, and a human review queue

**Dataset quality (post-validation):**

- 100 companies processed
- **89 passed** automated validation
- **11 flagged** for human review
- Average confidence: 0.88
- Average source quality: 0.97

### 2.3 Evaluation Framework

A complete eval harness (`app/evaluation/`) that:

- Loads OutboundBench CSV/JSONL as `EvaluationSample` objects with ground truth
- Runs the full LangGraph workflow per company (async, configurable concurrency)
- Scores each run across six metrics (see Section 4)
- Writes per-company `records.csv`, aggregate `summary.json`, and comparison charts
- Maintains run history in `app/evaluation/history/`
- Publishes canonical results to `data/benchmark_results.json`

---

## 3. Architecture Deep Dive

### 3.1 Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12+ |
| API framework | FastAPI |
| Agent orchestration | LangGraph (`StateGraph`) |
| Schemas / validation | Pydantic v2 |
| LLM | OpenAI (`gpt-4.1-mini`, structured outputs) |
| Web scraping | Firecrawl API |
| Web search | Tavily API |
| Database | PostgreSQL + SQLAlchemy (async) |
| Cache / workers | Redis + ARQ |
| Observability | OpenTelemetry, structured JSON logging |
| Infra | Docker, GitHub Actions CI |
| Package manager | uv |

### 3.2 Agent Descriptions

#### Research Agent
- **Input:** Company name, website URL
- **Process:** Calls `collect_company_evidence()` which scrapes the company homepage and key pages via Firecrawl, supplements with Tavily web search, classifies sources (website, blog, docs, careers, news), and formats an evidence block for the LLM
- **Output:** `CompanySummary` — industry, description, recent news, products, evidence URLs and snippets
- **Why it matters:** Everything downstream depends on research quality. This is the only agent that touches live web data directly.

#### ICP Agent
- **Input:** `CompanySummary` + `SellerProfile` (`config/seller_profile.json` — who "we" are, what we sell, target industries/size/buyer titles/disqualifiers)
- **Output:** ICP fit score (0–100) with reasoning that explicitly cites overlaps/mismatches with the seller's target profile
- **Evaluated against:** Ground-truth ICP target per company in OutboundBench (see Section 5.0 for why this comparison is now imperfect — the ground truth doesn't model a specific seller)

#### Pain Point Agent
- **Input:** Company summary + hiring trends
- **Output:** Top 3–5 pain points, each with description and messaging angle
- **Evaluated against:** Ground-truth pain point list (token overlap per pain)

#### Persona Agent
- **Input:** Company summary + ICP score + `SellerProfile` (as secondary context/tie-breaker only — see Section 5.0)
- **Output:** One of 8 buyer personas: `Founder`, `CEO`, `CTO`, `VP Engineering`, `Head of AI`, `VP Sales`, `RevOps`, `Product`
- **Evaluated against:** Natural-language ground-truth persona (e.g., "Designers and Design Teams", "Go-to-market teams including marketers and sales professionals")
- **Known limitation:** The enum is intentionally coarse for MVP; this is the main accuracy bottleneck (see Section 5)

#### Messaging Agent
- **Input:** Company summary, pain points, persona selection
- **Output:** `OutboundMessageBundle` — subject line + cold email body
- **Evaluated against:** Ground-truth pain points + reference outreach email

#### Reviewer Agent
- **Input:** Full message bundle + company context + quality threshold
- **Output:** `ReviewerCritique` — decision (APPROVE/REWRITE/RESEARCH), per-dimension scores, reasoning
- **Evaluated against:** Expected decision derived from research accuracy + email quality

### 3.3 LangGraph Workflow

The graph (`app/graph/builder.py`) implements:

- **Linear pipeline:** research → icp → pain → persona → email → reviewer
- **Conditional routing from reviewer:**
  - APPROVE → END
  - REWRITE → regenerate email → reviewer (up to `max_iterations`)
  - RESEARCH → back to research node → full pipeline rerun
- **Persona router:** If a prior review failed with RESEARCH decision, skip straight to rewrite on retry
- **Metrics tracking:** Per-node latency, estimated token usage, and cost accumulated in workflow state

### 3.4 Evidence Collection (Shared Infrastructure)

`app/tools/company_evidence.py` is shared between the OutboundBench dataset builder and the live Research Agent. This ensures the eval dataset and the agent pipeline use the same evidence-gathering logic — a deliberate choice to avoid train/serve skew in the research layer.

Evidence collection:
1. Normalize website URL
2. Firecrawl: scrape homepage + discover linked pages (about, careers, blog, docs, pricing, customers)
3. Tavily: supplemental web search for company news and context
4. Classify each source by type
5. Extract text snippets (up to 400 chars per source)
6. Return `CompanyEvidence` bundle with scrape error tracking

### 3.5 Production Scaffold (Beyond the Agent Core)

The repository also includes infrastructure typically expected in a production GTM platform:

- FastAPI REST API with health checks and ops endpoints
- SSE streaming for workflow progress (`/api/v1/ops/stream`)
- Background evaluation jobs via ARQ worker queue
- Redis caching layer
- OpenTelemetry distributed tracing
- Rate limiting middleware (SlowAPI)
- Docker Compose for API, worker, PostgreSQL, Redis, OTel collector
- GitHub Actions CI (lint, typecheck, test)
- React dashboard, wired to the live API via SSE streaming (requires running the backend + Vite dev server locally)

---

## 4. Evaluation Methodology

### 4.1 Official Baseline Run

| Parameter | Value |
|-----------|-------|
| Run ID | `eval-20260711-145039` |
| Date | 2026-07-11 |
| Dataset | OutboundBench (100 companies) |
| Agent mode | Live (Firecrawl + Tavily + OpenAI) |
| Concurrency | 2 |
| Quality threshold | 0.75 |
| Total runtime | ~43 minutes (slower than the prior ~33 min baseline — this run hit intermittent Tavily search failures, absorbed gracefully but with retry latency) |
| Total estimated cost | ~$0.90 |

### 4.2 Metric Definitions

All metrics are in [0, 1]. Higher is better.

#### Research Accuracy
Token overlap between the agent's predicted industry label and the ground-truth industry from OutboundBench. Exact string match = 1.0; partial overlap requires ≥30% token intersection.

**Result: 98%** (2/100 companies missed: Ramp, Supabase)

#### ICP Accuracy
`1 - |predicted_icp_score - ground_truth_target| / 100`

**Result: 72%** — down from a prior 91% baseline. See Section 5.0 for the full explanation: the ICP agent was fixed to score against an explicit seller profile instead of scoring in a vacuum, and OutboundBench's `icp_target` ground truth is itself seller-agnostic, so the two now measure subtly different things.

#### Pain Point Accuracy
For each ground-truth pain point, check if any predicted pain point has sufficient token overlap (≥20% of GT tokens, minimum 2 tokens). Score = fraction of GT pains matched.

**Result: 87%**

#### Persona Accuracy
Maps both the agent's enum output (e.g., `VP Sales`) and the ground-truth text (e.g., "Go-to-market teams including marketers and sales professionals") into role families: sales, marketing, engineering, finance, executive, product, data, security, etc. Family overlap = 1.0; token-only overlap capped at 0.5.

**Result: 29%** (29/100 companies with family match) — up slightly from a prior 27% baseline, after fixing a prompt bug where the persona agent initially collapsed to picking one dominant persona for nearly every company once seller context was added (see Section 5.0).

Companies where persona matched perfectly include: HubSpot, Datadog, DocuSign, Gong, Outreach, Salesloft, Clari, Amplitude, Mixpanel, Segment, LaunchDarkly, HashiCorp, GitLab, Salesforce, PagerDuty, New Relic, Drift, Apollo.io, 6sense, Demandbase, Calendly, Linear, Neon, Bitbucket, JFrog, CircleCI, Buildkite, Harness, Lucidchart — predominantly GTM/sales/revops/dev-tooling-oriented companies where the agent's pick aligns with ground truth.

Companies that consistently miss include: Stripe (finance/business owners), Notion (project managers), Figma (designers), Snowflake (data teams) — personas outside the current enum and family map. This ceiling is a product design gap (coarse enum), not something the seller-profile fix could address.

#### Email Quality (v2 composite metric)
Replaced raw `SequenceMatcher` string similarity, which produced misleadingly low scores (~6% on v1). The v2 composite weights:

| Signal | Weight |
|--------|--------|
| Company name present in email | 20% |
| Pain-point token overlap | 40% |
| Fact overlap with reference outreach | 25% |
| CTA detected (call, chat, meet, etc.) | 15% |

**Result: 96%**

#### Reviewer Agreement
Compares the reviewer's actual decision (APPROVE/REWRITE/RESEARCH) against an expected decision derived from research accuracy and email quality. Partial credit (0.5) for borderline cases.

**Result: 98%**

### 4.3 What the Numbers Mean (Honest Interpretation)

**Strong and credible:**
- **Research (98%):** The system reliably identifies the correct industry from live web evidence for 98/100 B2B companies. The 2 misses (Ramp, Supabase) this run were transient research failures, not the same edge cases as the prior baseline (MongoDB/Iterable/Vercel, which now score 1.0) — a reminder that live-agent runs have some run-to-run variance.
- **Pain points (87%):** Agents find real, evidence-backed business pains that overlap with ground truth most of the time.
- **Email (96%):** Generated emails reference company name, incorporate pain points, include facts from reference outreach, and have CTAs. This measures *grounding and structure*, not subjective "would I send this?" quality.
- **Reviewer (98%):** The quality gate works — reviewer decisions align with expected outcomes given research and email scores.

**Changed on purpose, not a regression:**
- **ICP (72%, down from 91%):** The ICP agent now scores fit against an explicit `SellerProfile` instead of a generic "does this look like a good company" heuristic — a real product gap that was found and fixed. OutboundBench's ground truth `icp_target` is itself generic/seller-agnostic (rewards SaaS/fintech/devtools/cybersecurity broadly, no concept of a specific seller), so a genuinely more correct, seller-anchored score will diverge from it for companies outside that seller's specific target market. This is a benchmark methodology limitation exposed by fixing the agent, not evidence the agent got worse.

**Weak and acknowledged:**
- **Persona (29%):** The agent picks from 8 buyer roles; ground truth uses rich natural-language descriptions. A `CTO` does not match "Designers and Design Teams" even with family matching. This is a product design gap, not just a metric issue. Adding seller context helped marginally (27% → 29%) but didn't fundamentally change this ceiling — see Section 5.0 for the two-iteration debugging story behind that number.

**Not measured:**
- Human preference ("would a real prospect reply?")
- Hallucination rate beyond outreach validation
- A/B conversion metrics
- Multi-touch sequence quality

### 4.4 Metric Version History

| Run | n | Notes |
|-----|---|-------|
| `eval-20260706-040559` | 100 | Pre-v2 metrics; email 6%, reviewer 0% (misleading due to raw string similarity) |
| `eval-20260706-041432` | 5 | v2 smoke test; email 97%, reviewer 100% |
| `eval-20260706-045418` | 100 | v2 metrics, pre seller-profile fix; ICP 91%, persona 27% |
| **`eval-20260711-145039`** | **100** | **Official baseline — v2 metrics + seller-profile-aware ICP/Persona** |

Do not compare email/reviewer scores across v1 and v2 runs. Do not compare ICP/persona scores across the seller-profile fix without the context in Section 5.0 — the numbers moved because what's being measured changed, not because agent quality changed.

---

## 5. Known Limitations & Future Work

### 5.0 The Seller-Profile Fix (and why fixing a real gap made a number go down)

Mid-project, a simple question exposed a real gap: *the ICP agent scores "is this a good fit for us to sell to" — but what does it actually know about "us"?* The answer, before July 11, 2026: nothing. `ICPAgentInput` only carried a `CompanySummary`; the prompt said "score B2B companies for outbound ICP fit" with no target industries, no target company size, no target buyer titles. It was measuring "how impressive/well-documented is this company," not "is this company a good fit for a specific seller" — a subtly different, less useful question.

**The fix:** a `SellerProfile` schema (`app/schemas/seller_profile.py`) — company name, product description, target industries, target company size, target geographies, ideal tech signals, target buyer titles, disqualifiers — loaded from an editable config file (`config/seller_profile.json`) via `app/utils/seller_profile.py`. It defaults to describing OutboundOS itself. This flows through `OutboundWorkflowState` into both the ICP and Persona prompts.

**First attempt overcorrected, and the debugging is worth telling honestly:**
1. First pass: the persona prompt said to pick "whichever enum value is closest to who the seller targets." Result: the agent picked `VP Sales` for nearly every company regardless of fit — persona accuracy dropped from 27% to 16%. Diagnosed by inspecting per-company records: every non-sales-tech company scored 0.0, every sales/martech company scored 1.0 — a dead giveaway of a collapsed, non-diverse output.
2. Second pass: reworded to make seller context "secondary" and company signals "primary" — but the LLM then collapsed onto a *different* single answer, `Head of AI`, because some mention of AI features is nearly universal in 2026 marketing copy and the prompt happened to name it as a signal to check.
3. Third pass (final): explicitly told the model to weigh multiple signals holistically, called out that AI-feature mentions alone are not decisive, and gave concrete industry→persona mapping examples. Verified real diversity returned via live spot-checks (Product, CTO, VP Sales across different companies) before committing to a full 100-company rerun.

**The ICP side of the fix was correct on the first attempt, and it made the benchmark's ICP accuracy score go down (91% → 72%) — deliberately, and that's the right outcome, not a bug.** OutboundBench's `icp_target` ground truth (`app/evaluation/outboundbench_loader.py::_estimate_icp_target`) is a generic heuristic that rewards SaaS/fintech/devtools/cybersecurity industries broadly, with zero concept of a specific seller. Once the agent started scoring fit against a real, narrower seller profile (B2B SaaS / sales-tech / martech / RevOps tooling, targeting VP Sales / RevOps / CRO buyers), it correctly scored fintech, cloud infra, and devtools companies lower — because they're a worse fit for *this specific seller*, even though the generic ground truth still expects them to score well. The agent and the benchmark are now answering two different implicit questions, and no further "fix" can close that gap without giving OutboundBench ground truth that's itself parameterized by a seller profile.

This is a genuinely good story for a walkthrough: it shows real gap-finding (not just running the happy path), an honest account of getting the fix wrong twice before diagnosing it from data, and a clear-eyed explanation of why "more correct" and "higher benchmark score" aren't always the same thing.

### 5.1 Persona Selection (Primary Gap)
The persona agent outputs one of 8 enum values. Ground truth uses descriptions like "team managers, project managers, knowledge workers" or "Designers and Design Teams." Expanding the enum (CFO, VP Marketing, Head of Data, Design Lead) and improving the persona agent prompt would directly address the 29% accuracy.

### 5.2 Cost Tracking
Token and cost estimates use a word-count heuristic (`len(payload.split()) * 2`), not actual OpenAI billing API responses. Directionally correct (~$0.009/company) but not audit-grade.

### 5.3 No Incremental Checkpointing
The OutboundBench build pipeline and eval runner process all companies in memory and export at the end. A Ctrl+C mid-run loses progress.

### 5.4 Dashboard Requires Local Setup
A React dashboard is wired to the live backend via Server-Sent Events (`/api/v1/ops/stream`) — it drives the real 6-agent LangGraph workflow and streams real per-agent results card-by-card as they finish. It started as a static mockup with hardcoded fake data; that was a follow-up fix, not the original state. The remaining limitation: it requires running the FastAPI backend and the Vite dev server side-by-side locally — there's no hosted one-click version.

### 5.5 No Production Deployment
The system runs locally / in Docker. There is no public demo URL or hosted instance.

### 5.6 Research Edge Cases
2/100 companies had research failures on the current official run (Ramp, Supabase). The specific companies that miss vary somewhat run-to-run with live agents (the prior baseline's misses — MongoDB, Iterable, Vercel — all scored 1.0 this run); the common thread is industry extraction struggling when companies span multiple categories or when supplemental web search has transient failures.

---

## 6. Example: End-to-End Flow (Stripe)

**Input:** `Stripe`, `https://stripe.com`

**Ground truth (from OutboundBench):**
- Industry: Financial Technology (FinTech)
- Persona: Business owners, finance teams, and software platform operators
- Pain: Cross-border payment complexity, scaling financial infrastructure, B2B payment integration
- Reference email: Mentions Stripe's GDP metric, cross-border payment challenges, offers a call

**Agent output (eval-20260711-145039, post seller-profile fix):**
- Research accuracy: **1.0** (industry matched)
- ICP accuracy: **0.65** (agent correctly scores Stripe as a moderate/weak fit for OutboundOS's seller profile — Stripe is fintech, not sales-tech/martech/RevOps-tooling — while the generic ground truth still expects a fintech-favorable score; see Section 5.0)
- Persona accuracy: **0.0** (agent picked a persona outside the finance/business-owner family, e.g. `Product` or `CTO`)
- Pain point accuracy: **1.0** (all GT pains covered)
- Email quality: **1.0** (company name, pains, facts, CTA all present)
- Reviewer agreement: **1.0**

This pattern — strong research/pain/email, weaker ICP-vs-generic-ground-truth and weak persona — is representative of most companies in the benchmark. It's also a clean illustration of the ICP finding in Section 5.0: Stripe is a great company by any generic measure, but a genuinely mediocre fit for a seller whose actual target market is sales/RevOps tooling buyers — and the fixed agent now says so.

---

## 7. How to Reproduce

### Prerequisites
```bash
cp .env.example .env
# Set: OPENAI_API_KEY, FIRECRAWL_API_KEY, TAVILY_API_KEY
# Set: BENCHMARK_MODE=false
uv sync
```

### Run evaluation
```bash
# Full 100-company eval (~33 min, ~$0.88)
make eval-outboundbench

# Smoke test (5 companies, ~3 min)
uv run python -m app.evaluation.run \
  --dataset data/outboundbench_companies.csv \
  --dataset-size 5 \
  --max-concurrency 2 \
  --quality-threshold 0.75
```

### Publish results
```bash
uv run python -m app.evaluation.publish_benchmark \
  app/evaluation/history/<run-id>/summary.json
```

### Run tests
```bash
make check   # lint + typecheck + pytest (22 tests)
```

---

## 8. Project Structure

```
OutboundOS/
├── app/
│   ├── agents/           # 6 agents + prompts + LLM output schemas
│   ├── api/              # FastAPI routes
│   ├── dataset/          # OutboundBench build pipeline
│   ├── evaluation/       # Eval runner, metrics, loader, publish
│   ├── graph/            # LangGraph workflow builder + state
│   ├── schemas/          # Pydantic models (shared across agents)
│   ├── tools/            # Firecrawl, Tavily, LLM client, evidence
│   └── workers/          # ARQ background jobs
├── data/
│   ├── outboundbench_companies.csv    # 100-company eval dataset
│   └── benchmark_results.json         # Official published scores
├── docs/
│   ├── BENCHMARK.md                   # Methodology + results reference
│   └── PROJECT_WRITEUP.md             # This document
├── tests/                # Unit tests (dataset, agents, evaluation)
├── dashboard/            # React UI, wired to the live API via SSE streaming
├── config/
│   └── seller_profile.json            # Who "we" are — target industries, buyer titles, etc.
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## 9. What This Demonstrates

For a technical reviewer, this project shows:

1. **Multi-agent system design** — decomposed responsibilities, structured outputs, conditional routing with feedback loops
2. **Evidence-grounded AI** — web scraping + search + LLM extraction, not pure parametric knowledge
3. **Evaluation rigor** — custom benchmark dataset, six metrics, reproducible baselines, honest reporting of gaps
4. **Dataset engineering** — automated pipeline from seed list to validated ground truth with human review queue
5. **Production awareness** — API, workers, observability, Docker, CI (even if not fully deployed)
6. **Cost/latency consciousness** — tracked per company, optimized for batch eval at ~$0.009/account
7. **Intellectual honesty** — persona gap documented, metric versions tracked, v1/v2 scores not conflated, and a benchmark-vs-agent mismatch (Section 5.0) explained rather than hidden

---

## 10. Suggested Talking Points (Interviews)

- "I built a 6-agent LangGraph pipeline that researches B2B companies from live web data and drafts personalized outbound emails."
- "I created OutboundBench, a 100-company evaluation dataset with evidence URLs and automated validation — 89% passed without human review."
- "On the held-out benchmark, research accuracy is 98% and pain-point accuracy is 87%, at under a cent per company (~$0.009)."
- "The main gap is persona selection at 29% — the agent uses a coarse buyer enum while ground truth uses natural-language roles. That's my highest-priority improvement."
- "I iterated on evaluation metrics itself — early string-similarity scoring gave 6% email accuracy which was misleading; I replaced it with a semantic composite that better reflects outreach quality."
- "Midway through, I found the ICP agent had zero information about who 'we' are — it couldn't actually judge fit for a specific seller. I fixed it by adding an explicit seller profile, and it's a good example of a fix that made a benchmark number go down (ICP 91%→72%) for well-understood, defensible reasons rather than up — the ground truth itself doesn't model any specific seller."

---

## Appendix A: Official Results (Full Table)

**Run:** `eval-20260711-145039` · **Published:** 2026-07-11

| Metric | Value |
|--------|-------|
| research_accuracy | 0.9800 |
| icp_accuracy | 0.7215 |
| pain_point_accuracy | 0.8700 |
| persona_accuracy | 0.2900 |
| email_quality | 0.9643 |
| reviewer_agreement | 0.9750 |
| avg_latency_ms | 50,890.7 |
| avg_cost_usd | 0.009035 |
| avg_tokens | 3,614.0 |

**Prior baseline (pre seller-profile fix), for context:** `eval-20260706-045418` — research 0.9700, icp 0.9110, pain 0.8908, persona 0.2700, email 0.9620, reviewer 0.9650. See Section 5.0 for why ICP moved and persona barely moved.

## Appendix B: Persona Matches (29/100)

HubSpot, Datadog, DocuSign, Gong, Outreach, Salesloft, Clari, Amplitude, Mixpanel, Segment, LaunchDarkly, HashiCorp, GitLab, Salesforce, PagerDuty, New Relic, Drift, Apollo.io, 6sense, Demandbase, Calendly, Linear, Neon, Bitbucket, JFrog, CircleCI, Buildkite, Harness, Lucidchart

## Appendix C: Research Failures (2/100)

Ramp, Supabase

(Prior baseline's misses — MongoDB, Iterable, Vercel — all scored 1.0 on this run; live-agent runs have some run-to-run variance in exactly which edge cases trip up research.)

---

*This document is the canonical project narrative. For live metric values, always refer to [`data/benchmark_results.json`](../data/benchmark_results.json).*
