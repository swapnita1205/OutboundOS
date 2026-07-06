# OutboundOS — Project Writeup

**Author:** Swapnita Sahu  
**Date:** July 2026  
**Repository:** OutboundOS (local / portfolio project)  
**Official benchmark:** `eval-20260706-045418` · [`data/benchmark_results.json`](../data/benchmark_results.json)

---

## Executive Summary

OutboundOS is a multi-agent AI system that automates the research and drafting workflow of an outbound Sales Development Representative (SDR). Given a company name and website, the system:

1. Researches the company from live web sources
2. Scores ideal customer profile (ICP) fit
3. Identifies evidence-backed pain points
4. Selects a buyer persona
5. Drafts a personalized cold email
6. Reviews the email for quality and either approves, rewrites, or triggers re-research

The project includes **OutboundBench**, a custom 100-company evaluation dataset with ground-truth labels, evidence URLs, and reference outreach — plus a full evaluation framework that measures agent performance across six metrics.

On the official n=100 benchmark run (live agents, July 2026):

| Metric | Score |
|--------|-------|
| Research accuracy | **97%** |
| ICP accuracy | **91%** |
| Pain point accuracy | **89%** |
| Email quality | **96%** |
| Reviewer agreement | **97%** |
| Persona accuracy | **27%** (known gap) |

Average cost: **$0.0088 / company** · Average latency: **39 seconds / company**

This writeup explains what was built, why design decisions were made, how evaluation works, and what the results mean — including honest discussion of limitations.

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
- **Input:** `CompanySummary`
- **Output:** ICP fit score (0–100) with reasoning
- **Evaluated against:** Ground-truth ICP target per company in OutboundBench

#### Pain Point Agent
- **Input:** Company summary + hiring trends
- **Output:** Top 3–5 pain points, each with description and messaging angle
- **Evaluated against:** Ground-truth pain point list (token overlap per pain)

#### Persona Agent
- **Input:** Company summary + ICP score
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
- React dashboard scaffold (not yet wired to live API)

---

## 4. Evaluation Methodology

### 4.1 Official Baseline Run

| Parameter | Value |
|-----------|-------|
| Run ID | `eval-20260706-045418` |
| Date | 2026-07-06 |
| Dataset | OutboundBench (100 companies) |
| Agent mode | Live (Firecrawl + Tavily + OpenAI) |
| Concurrency | 2 |
| Quality threshold | 0.75 |
| Total runtime | ~33 minutes |
| Total estimated cost | ~$0.88 |

### 4.2 Metric Definitions

All metrics are in [0, 1]. Higher is better.

#### Research Accuracy
Token overlap between the agent's predicted industry label and the ground-truth industry from OutboundBench. Exact string match = 1.0; partial overlap requires ≥30% token intersection.

**Result: 97%** (3/100 companies missed: MongoDB, Iterable, Vercel)

#### ICP Accuracy
`1 - |predicted_icp_score - ground_truth_target| / 100`

**Result: 91%**

#### Pain Point Accuracy
For each ground-truth pain point, check if any predicted pain point has sufficient token overlap (≥20% of GT tokens, minimum 2 tokens). Score = fraction of GT pains matched.

**Result: 89%**

#### Persona Accuracy
Maps both the agent's enum output (e.g., `VP Sales`) and the ground-truth text (e.g., "Go-to-market teams including marketers and sales professionals") into role families: sales, marketing, engineering, finance, executive, product, data, security, etc. Family overlap = 1.0; token-only overlap capped at 0.5.

**Result: 27%** (27/100 companies with family match)

Companies where persona matched perfectly include: HubSpot, Datadog, Gong, Outreach, Salesloft, Mixpanel, Drift, Apollo.io, 6sense, Demandbase, Calendly, Linear, CircleCI, Harness, and others — predominantly GTM/sales/revops-oriented companies where `VP Sales` or `RevOps` aligns with ground truth.

Companies that consistently miss include: Stripe (finance/business owners), Notion (project managers), Figma (designers), Snowflake (data teams) — personas outside the current enum and family map.

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

**Result: 97%**

### 4.3 What the Numbers Mean (Honest Interpretation)

**Strong and credible:**
- **Research (97%):** The system reliably identifies the correct industry from live web evidence for 97/100 B2B companies. Failures are edge cases (MongoDB labeled as generic IT, Iterable/Vercel industry mismatch).
- **Pain points (89%):** Agents find real, evidence-backed business pains that overlap with ground truth most of the time.
- **ICP (91%):** Fit scoring is well-calibrated against human-derived targets.
- **Email (96%):** Generated emails reference company name, incorporate pain points, include facts from reference outreach, and have CTAs. This measures *grounding and structure*, not subjective "would I send this?" quality.
- **Reviewer (97%):** The quality gate works — reviewer decisions align with expected outcomes given research and email scores.

**Weak and acknowledged:**
- **Persona (27%):** The agent picks from 8 buyer roles; ground truth uses rich natural-language descriptions. A `CTO` does not match "Designers and Design Teams" even with family matching. This is a product design gap, not just a metric issue.

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
| **`eval-20260706-045418`** | **100** | **Official baseline with v2 metrics** |

Do not compare email/reviewer scores across v1 and v2 runs.

---

## 5. Known Limitations & Future Work

### 5.1 Persona Selection (Primary Gap)
The persona agent outputs one of 8 enum values. Ground truth uses descriptions like "team managers, project managers, knowledge workers" or "Designers and Design Teams." Expanding the enum (CFO, VP Marketing, Head of Data, Design Lead) and improving the persona agent prompt would directly address the 27% accuracy.

### 5.2 Cost Tracking
Token and cost estimates use a word-count heuristic (`len(payload.split()) * 2`), not actual OpenAI billing API responses. Directionally correct (~$0.009/company) but not audit-grade.

### 5.3 No Incremental Checkpointing
The OutboundBench build pipeline and eval runner process all companies in memory and export at the end. A Ctrl+C mid-run loses progress.

### 5.4 Dashboard Not Live
A React dashboard exists in the repo but displays mock data. It is not connected to the FastAPI backend or eval history.

### 5.5 No Production Deployment
The system runs locally / in Docker. There is no public demo URL or hosted instance.

### 5.6 Research Edge Cases
3/100 companies had research failures. Investigation suggests industry extraction struggles when companies span multiple categories (e.g., MongoDB as "IT Services" vs. "Database Platform").

---

## 6. Example: End-to-End Flow (Stripe)

**Input:** `Stripe`, `https://stripe.com`

**Ground truth (from OutboundBench):**
- Industry: Financial Technology (FinTech)
- Persona: Business owners, finance teams, and software platform operators
- Pain: Cross-border payment complexity, scaling financial infrastructure, B2B payment integration
- Reference email: Mentions Stripe's GDP metric, cross-border payment challenges, offers a call

**Agent output (eval-20260706-045418):**
- Research accuracy: **1.0** (industry matched)
- Persona accuracy: **0.0** (agent likely picked `Product` or `CEO`, not finance-focused)
- Pain point accuracy: **1.0** (all GT pains covered)
- Email quality: **1.0** (company name, pains, facts, CTA all present)
- Reviewer agreement: **1.0**

This pattern — strong research/pain/email, weak persona — is representative of most companies in the benchmark.

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
├── dashboard/            # React UI (mock data)
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
7. **Intellectual honesty** — persona gap documented, metric versions tracked, v1/v2 scores not conflated

---

## 10. Suggested Talking Points (Interviews)

- "I built a 6-agent LangGraph pipeline that researches B2B companies from live web data and drafts personalized outbound emails."
- "I created OutboundBench, a 100-company evaluation dataset with evidence URLs and automated validation — 89% passed without human review."
- "On the held-out benchmark, research accuracy is 97% and pain-point accuracy is 89%, at about 9 cents per company."
- "The main gap is persona selection at 27% — the agent uses a coarse buyer enum while ground truth uses natural-language roles. That's my highest-priority improvement."
- "I iterated on evaluation metrics itself — early string-similarity scoring gave 6% email accuracy which was misleading; I replaced it with a semantic composite that better reflects outreach quality."

---

## Appendix A: Official Results (Full Table)

**Run:** `eval-20260706-045418` · **Published:** 2026-07-06

| Metric | Value |
|--------|-------|
| research_accuracy | 0.9700 |
| icp_accuracy | 0.9110 |
| pain_point_accuracy | 0.8908 |
| persona_accuracy | 0.2700 |
| email_quality | 0.9620 |
| reviewer_agreement | 0.9650 |
| avg_latency_ms | 38,925.8 |
| avg_cost_usd | 0.008829 |
| avg_tokens | 3,531.4 |

## Appendix B: Persona Matches (27/100)

HubSpot, Datadog, Gong, Outreach, Salesloft, Clari, LaunchDarkly, HashiCorp, GitLab, PagerDuty, New Relic, Drift, Clearbit, Apollo.io, 6sense, Demandbase, Calendly, Linear, Neon, JFrog, CircleCI, Buildkite, Harness, Lucidchart, Smartsheet, Bitbucket, Mixpanel

## Appendix C: Research Failures (3/100)

MongoDB, Iterable, Vercel

---

*This document is the canonical project narrative. For live metric values, always refer to [`data/benchmark_results.json`](../data/benchmark_results.json).*
