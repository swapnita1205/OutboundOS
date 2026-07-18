# OutboundOS — Project Writeup

**Author:** Swapnita Sahu  
**Date:** July 2026  
**Repository:** OutboundOS (local / portfolio project)  
**Official benchmark:** `eval-20260718-232055` · [`data/benchmark_results.json`](../data/benchmark_results.json)

---

## Executive Summary

OutboundOS is a multi-agent AI system that automates the research and drafting workflow of an outbound Sales Development Representative (SDR). Given a company name and website, the system:

1. Researches the company from live web sources
2. Scores ideal customer profile (ICP) fit **against an explicit seller profile** (who "we" are, what we sell, who we target)
3. Identifies evidence-backed pain points
4. Selects a buyer persona
5. Drafts a personalized cold email
6. Reviews the email for quality and either approves, rewrites, or triggers re-research

The project includes **OutboundBench**, a custom 100-company evaluation dataset with **human-authored** ground-truth labels, evidence URLs, and reference outreach — plus a full evaluation framework that measures agent performance across six metrics, including a semantic (embedding-based) scorer that credits paraphrases rather than only exact wording.

On the official n=100 benchmark run (live agents, July 2026):

| Metric | Score |
|--------|-------|
| Research accuracy | **96%** |
| Email quality | **83%** |
| Reviewer agreement | **88%** |
| ICP accuracy | **82%** |
| Pain point accuracy | **70%** |
| Persona accuracy | **49%** (known gap) |

Average cost: **~$0.011 / company** · Average latency: **~35 seconds / company**

This writeup explains what was built, why design decisions were made, how evaluation works, and what the results mean — including honest discussion of limitations. Two evaluation-quality decisions are worth calling out up front and are detailed in Section 5: (1) the ground truth is **authored by hand from real web evidence**, so the benchmark measures agent quality against an independent source of truth rather than agreement between two models; and (2) the pain-point/email metric was upgraded from pure token overlap to a **paraphrase-aware semantic scorer**, because token overlap unfairly scored correct-but-differently-worded answers as zero.

---

## 1. Problem Statement

Outbound sales is labor-intensive. A human SDR typically spends 15–30 minutes per account researching a company, identifying relevant pain points, choosing the right buyer persona, and drafting a personalized email. At scale, this becomes expensive, inconsistent, and hard to measure.

The core question this project addresses:

> **Can a multi-agent LLM system perform evidence-grounded outbound research and messaging at useful accuracy, with measurable quality and reasonable cost?**

Most demo-grade "AI SDR" projects skip rigorous evaluation — they show one polished example email and call it done. OutboundOS was built with evaluation as a first-class concern: an evaluation dataset with independent human-authored ground truth, per-metric scoring, run history, and reproducible baselines.

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

A 100-company B2B evaluation dataset spanning SaaS categories: CRM, dev tools, fintech, security, marketing automation, productivity, data platforms, and more (Stripe, HubSpot, Snowflake, Datadog, Gong, etc.).

**Each record contains:**

| Field | Purpose |
|-------|---------|
| `company_name`, `website` | Target account |
| `industry`, `short_description` | Ground-truth company profile |
| `target_persona` | Natural-language buyer description |
| `pain_points` | Evidence-backed pain points |
| `evidence_urls` | Source URLs the labels were derived from |
| `evidence_snippets` | Text excerpts from those sources |
| `reference_outreach` | Reference cold email |

**How the ground truth is built:**

1. **Evidence collection** — for each company, collect live web evidence (Firecrawl page scrapes of homepage/about/careers/blog/docs/pricing/customers + Tavily search), classified by source type. This is the same evidence-gathering tooling the live Research Agent uses.
2. **Human labeling** — from that evidence, the ground-truth fields (industry, description, persona, pain points, reference outreach) are **authored by hand** in a labeling worksheet (`data/human_ground_truth/worksheet.csv`).
3. **Compile** — the filled worksheet is compiled into the dataset (`data/human_ground_truth/outboundbench_human.csv`) via `app/dataset/finalize_human_ground_truth.py`.

The deliberate point: the labels are **independent human judgment**, not the output of the same class of model the benchmark evaluates. That keeps the benchmark from rewarding an agent simply for phrasing things the way another LLM would (see Section 5.1).

### 2.3 Evaluation Framework

A complete eval harness (`app/evaluation/`) that:

- Loads OutboundBench CSV/JSONL as `EvaluationSample` objects with ground truth
- Runs the full LangGraph workflow per company (async, configurable concurrency)
- Scores each run across six metrics (see Section 4), including embedding-based semantic matching for pain points and email content
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
| LLM | OpenAI (`gpt-4.1-mini`, structured outputs) + `text-embedding-3-small` for eval |
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
- **Evaluated against:** A per-company ICP target (see Section 5.3 for why this comparison is intentionally imperfect — the benchmark target doesn't model a specific seller)

#### Pain Point Agent
- **Input:** Company summary + hiring trends
- **Output:** Top 3–5 pain points, each with description and messaging angle
- **Evaluated against:** Ground-truth pain point list (token overlap + semantic paraphrase match)

#### Persona Agent
- **Input:** Company summary + ICP score + `SellerProfile` (as secondary context/tie-breaker only — see Section 5.3)
- **Output:** One of 8 buyer personas: `Founder`, `CEO`, `CTO`, `VP Engineering`, `Head of AI`, `VP Sales`, `RevOps`, `Product`
- **Evaluated against:** Natural-language ground-truth persona (e.g., "Designers and Design Teams")
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

`app/tools/company_evidence.py` is shared between the OutboundBench evidence-gathering step and the live Research Agent. This ensures the eval dataset's evidence and the agent pipeline use the same evidence-gathering logic — a deliberate choice to avoid train/serve skew in the research layer.

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
| Run ID | `eval-20260718-232055` |
| Date | 2026-07-18 |
| Dataset | OutboundBench (100 companies, human-authored ground truth) |
| Agent mode | Live (Firecrawl + Tavily + OpenAI) |
| Concurrency | 2 |
| Quality threshold | 0.75 |
| Total runtime | ~30 minutes |
| Total estimated cost | ~$1.13 |

### 4.2 Metric Definitions

All metrics are in [0, 1]. Higher is better.

#### Research Accuracy
Token overlap between the agent's predicted industry label and the ground-truth industry. Exact string match = 1.0; partial overlap requires ≥30% token intersection.

**Result: 96%**

#### ICP Accuracy
`1 - |predicted_icp_score - ground_truth_target| / 100`

**Result: 82%** — see Section 5.3: the ICP agent scores against an explicit seller profile, while the benchmark's `icp_target` is a generic, seller-agnostic heuristic, so the two measure subtly different things.

#### Pain Point Accuracy
For each ground-truth pain point, take the **maximum** of (a) token overlap match and (b) embedding-cosine paraphrase match (`text-embedding-3-small`; full credit at ≥0.60 cosine, zero at ≤0.35, linear between). Score = mean over GT pains.

**Result: 70%**

#### Persona Accuracy
Maps both the agent's enum output (e.g., `VP Sales`) and the ground-truth text (e.g., "Go-to-market teams including marketers and sales professionals") into role families: sales, marketing, engineering, finance, executive, product, data, security, etc. Family overlap = 1.0; token-only overlap capped at 0.5.

**Result: 49%**

#### Email Quality (composite metric)
Weighted composite:

| Signal | Weight |
|--------|--------|
| Company name present in email | 20% |
| Pain-point coverage (token or embedding-cosine vs email sentences) | 40% |
| Fact overlap with reference outreach (token or whole-email cosine) | 25% |
| CTA detected (call, chat, meet, etc.) | 15% |

**Result: 83%**

#### Reviewer Agreement
Compares the reviewer's actual decision (APPROVE/REWRITE/RESEARCH) against an expected decision derived from research accuracy and email quality. Partial credit (0.5) for borderline cases.

**Result: 88%**

### 4.3 What the Numbers Mean (Honest Interpretation)

**Strong and credible:**
- **Research (96%):** The system reliably identifies the correct industry from live web evidence for the large majority of B2B companies. Live-agent runs have some run-to-run variance in exactly which companies trip up research (transient search/scrape failures).
- **Email (83%):** Generated emails reference company name, incorporate pain points, include facts from reference outreach, and have CTAs. This measures *grounding and structure*, not subjective "would I send this?" quality.
- **Reviewer (88%):** The quality gate works — reviewer decisions align with expected outcomes given research and email scores.

**Solid:**
- **Pain points (70%):** Agents find real, evidence-backed business pains that match the human-authored labels most of the time. This number is measured with paraphrase-aware scoring (Section 5.2); with pure token overlap on the same data it was 59%, and the gap is entirely correct-but-differently-worded pains.
- **ICP (82%):** Scored against a real seller profile; see Section 5.3 for the benchmark mismatch caveat.

**Weak and acknowledged:**
- **Persona (49%):** The agent picks from 8 buyer roles; ground truth uses rich natural-language descriptions. A `CTO` does not match "Designers and Design Teams" even with family matching. This is a product design gap, not just a metric issue.

**Not measured:**
- Human preference ("would a real prospect reply?")
- Hallucination rate beyond outreach validation
- A/B conversion metrics
- Multi-touch sequence quality

---

## 5. Key Evaluation-Quality Decisions & Limitations

### 5.1 Independent, human-authored ground truth

The single most important property of a benchmark is that its ground truth is a **more independent source of truth** than the thing being graded. OutboundBench's evidence is collected from real web sources, and its labels (industry, persona, pain points, reference outreach) are authored **by hand** from that evidence. This means the benchmark measures whether the agent got the answer *right*, not whether it happened to phrase things the way another model would. It also makes the accuracy claims defensible under scrutiny: the comparison is agent-vs-human, not model-vs-model.

### 5.2 The metric fix: token overlap → semantic (paraphrase-aware) scoring

The first version of the pain-point and email metrics used pure **token-set overlap with a threshold**. Against independent human labels, this systematically *under*-counted correct answers: a human might write "knowledge and workflows scattered across many disconnected tools" while the agent writes "teams struggle with fragmented information across separate apps" — the same pain, almost no shared tokens, scored as a total miss (0.0).

The fix (`app/evaluation/semantic.py`) embeds both sides with `text-embedding-3-small` and compares them by cosine similarity, mapped through a tolerance band: **≥ 0.60 cosine = full credit, ≤ 0.35 = zero, linear in between**. The final per-pain score is the **max** of token overlap and semantic match, so exact wording still scores 1.0 while genuine paraphrases now earn credit. The band was calibrated against real pairs — paraphrases land at ~0.59–0.61 cosine, unrelated pains at ~0.30. When no OpenAI key is available (CI/offline) or the embeddings call fails, scoring degrades gracefully to token overlap.

**The effect, measured on the same dataset and same agent:**

| Run | Pain scoring | Pain point | Email |
|-----|--------------|-----------|-------|
| `eval-20260718-224055` | token only | 59% | 76% |
| `eval-20260718-232055` (official) | token + semantic | **70%** | **83%** |

The agent did not change between these two runs — only the metric did. This is a clean demonstration of "match the metric to the thing you're measuring": token overlap was measuring vocabulary agreement, not semantic correctness.

Precise methodology framing (for depth questions): this is **not** Jaccard (no intersection/union) and **not** a single hard cutoff — it's token overlap as an exact-wording floor plus embedding cosine with a calibrated tolerance band for paraphrases.

### 5.3 Seller-profile-aware ICP/Persona (why ICP is a deliberate benchmark mismatch)

The ICP and Persona agents score/select relative to an explicit `SellerProfile` (`app/schemas/seller_profile.py`, configured via `config/seller_profile.json`) — target industries, company size, buyer titles, disqualifiers. It defaults to describing OutboundOS itself (an outbound-automation platform targeting B2B SaaS / sales-tech / martech / RevOps-tooling companies), and flows through `OutboundWorkflowState` into both the ICP and Persona prompts.

This is the correct behavior for a real deployment — "is this a good fit *for us*" is the actual business question. But it creates a deliberate mismatch with the benchmark: OutboundBench's `icp_target` (`app/evaluation/outboundbench_loader.py::_estimate_icp_target`) is a generic heuristic that rewards SaaS/fintech/devtools/cybersecurity broadly, with no concept of a specific seller. A genuinely seller-anchored score will diverge from it for companies outside that seller's target market — not because the agent is wrong, but because the two are answering different implicit questions. Closing this gap would require ground truth that is *also* parameterized by a seller profile.

Persona selection needed two rounds of prompt tuning to avoid collapsing onto a single dominant answer once seller context was added: the first attempt over-indexed on the seller's target buyer titles and picked "VP Sales" for nearly every company; the second collapsed onto "Head of AI" because AI-feature mentions are near-universal in 2026 marketing copy. The fix was to make company-specific signals (industry, product, tech stack) primary and the seller profile a secondary tie-breaker, verified by spot-checking real output diversity before a full rerun.

### 5.4 Persona Selection (Primary Gap)
The persona agent outputs one of 8 enum values. Ground truth uses descriptions like "team managers, project managers, knowledge workers" or "Designers and Design Teams." Expanding the enum (CFO, VP Marketing, Head of Data, Design Lead) and improving the persona agent prompt would directly address the 49% accuracy.

### 5.5 Cost Tracking
Token and cost estimates use a word-count heuristic (`len(payload.split()) * 2`), not actual OpenAI billing API responses. Directionally correct (~$0.011/company) but not audit-grade.

### 5.6 No Incremental Checkpointing
The eval runner processes all companies in memory and exports at the end. A Ctrl+C mid-run loses progress.

### 5.7 Dashboard Requires Local Setup
A React dashboard is wired to the live backend via Server-Sent Events (`/api/v1/ops/stream`) — it drives the real 6-agent LangGraph workflow and streams real per-agent results card-by-card as they finish. It requires running the FastAPI backend and the Vite dev server side-by-side locally; there's no hosted one-click version.

### 5.8 No Production Deployment
The system runs locally / in Docker. There is no public demo URL or hosted instance.

---

## 6. Example: End-to-End Flow (Stripe)

**Input:** `Stripe`, `https://stripe.com`

**Ground truth (human-authored, from Stripe's own site + evidence):**
- Industry: FinTech / Payments infrastructure
- Persona: Finance leaders, platform engineering teams, and product leads at software platforms
- Pain: Integrating/reconciling payments across products as the business scales, cross-border payment complexity, custom revenue models
- Reference email: Mentions Stripe's "financial infrastructure to grow revenue" positioning and offers a call

**Agent output pattern (official baseline):**
- Research accuracy: **1.0** (industry matched)
- ICP accuracy: moderate (agent correctly scores Stripe as a weaker fit for OutboundOS's specific seller profile — fintech, not sales-tech/RevOps-tooling — while the generic benchmark target still expects a fintech-favorable score; see Section 5.3)
- Persona accuracy: often 0.0 (agent picks a persona outside the finance/business-owner family)
- Pain point accuracy: high (GT pains covered, credited via semantic match even when phrased differently)
- Email quality: high (company name, pains, facts, CTA all present)
- Reviewer agreement: high

This pattern — strong research/pain/email, weaker ICP-vs-generic-target and weak persona — is representative of most companies in the benchmark.

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
# Full 100-company eval
make eval-outboundbench

# Smoke test (5 companies)
uv run python -m app.evaluation.run \
  --dataset data/human_ground_truth/outboundbench_human.csv \
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
make check   # lint + typecheck + pytest
```

---

## 8. Project Structure

```
OutboundOS/
├── app/
│   ├── agents/           # 6 agents + prompts + LLM output schemas
│   ├── api/              # FastAPI routes
│   ├── dataset/          # Ground-truth compilation + validators/schemas
│   ├── evaluation/       # Eval runner, metrics, semantic matcher, loader, publish
│   ├── graph/            # LangGraph workflow builder + state
│   ├── schemas/          # Pydantic models (shared across agents)
│   ├── tools/            # Firecrawl, Tavily, LLM client, evidence
│   └── workers/          # ARQ background jobs
├── data/
│   ├── human_ground_truth/
│   │   ├── outboundbench_human.csv   # 100-company human-authored dataset
│   │   └── worksheet.csv             # Evidence + human-authored labels
│   └── benchmark_results.json        # Official published scores
├── docs/
│   ├── BENCHMARK.md                  # Methodology + results reference
│   └── PROJECT_WRITEUP.md            # This document
├── tests/                # Unit tests (dataset, agents, evaluation)
├── dashboard/            # React UI, wired to the live API via SSE streaming
├── config/
│   └── seller_profile.json           # Who "we" are — target industries, buyer titles, etc.
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## 9. What This Demonstrates

For a technical reviewer, this project shows:

1. **Multi-agent system design** — decomposed responsibilities, structured outputs, conditional routing with feedback loops
2. **Evidence-grounded AI** — web scraping + search + LLM extraction, not pure parametric knowledge
3. **Evaluation rigor** — a benchmark with independent human-authored ground truth, six metrics, reproducible baselines, honest reporting of gaps
4. **Metric design** — a semantic scorer that measures meaning rather than vocabulary, with the before/after numbers to prove it mattered
5. **Production awareness** — API, workers, observability, Docker, CI (even if not fully deployed)
6. **Cost/latency consciousness** — tracked per company, optimized for batch eval at ~$0.011/account
7. **Intellectual honesty** — persona gap documented, metric methodology stated precisely, benchmark-vs-agent ICP mismatch explained rather than hidden

---

## 10. Suggested Talking Points (Interviews)

- "I built a 6-agent LangGraph pipeline that researches B2B companies from live web data and drafts personalized outbound emails."
- "I created OutboundBench, a 100-company evaluation dataset where the ground truth is authored by hand from real web evidence — so the benchmark measures the agent against independent human judgment, not against another model."
- "On the benchmark, research accuracy is 96% and pain-point accuracy is 70%, at ~$0.011 per company."
- "The main gap is persona selection at 49% — the agent uses a coarse buyer enum while ground truth uses natural-language roles. That's my highest-priority improvement."
- "I found my pain-point metric was scoring correct paraphrases as zero because it only did token overlap. I added embedding-cosine scoring with a calibrated tolerance band, and pain-point accuracy went from 59% to 70% on the same data and same agent — the number moved because the metric got more correct, not because the agent changed."
- "ICP scoring is grounded in an explicit seller profile, which is more correct for a real deployment but deliberately diverges from a generic, seller-agnostic benchmark target — a mismatch I can explain rather than hide."

---

## Appendix A: Official Results (Full Table)

**Run:** `eval-20260718-232055` · **Published:** 2026-07-18

| Metric | Value |
|--------|-------|
| research_accuracy | 0.9600 |
| icp_accuracy | 0.8163 |
| pain_point_accuracy | 0.7009 |
| persona_accuracy | 0.4900 |
| email_quality | 0.8335 |
| reviewer_agreement | 0.8800 |
| avg_latency_ms | 35,320.5 |
| avg_cost_usd | 0.011252 |
| avg_tokens | 4,500.6 |

**Metric-methodology comparison (same dataset, n=100):** `eval-20260718-224055` (token-only pain/email scoring) scored pain 0.59 / email 0.76; the official run above uses paraphrase-aware semantic scoring. Same agent, different metric.

---

*This document is the canonical project narrative. For live metric values, always refer to [`data/benchmark_results.json`](../data/benchmark_results.json).*
