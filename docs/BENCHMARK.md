# OutboundBench & Evaluation Results

Single source of truth for OutboundOS benchmark methodology, metrics, and official scores.

**Canonical artifact:** [`data/benchmark_results.json`](../data/benchmark_results.json)

---

## OutboundBench Dataset

OutboundBench is a 100-company, evidence-grounded evaluation dataset for AI outbound SDR agents. Each record includes:

| Field | Description |
|-------|-------------|
| `company_name`, `website` | Target account |
| `industry`, `short_description` | Ground-truth company profile |
| `target_persona` | Natural-language buyer persona (not a fixed enum) |
| `pain_points` | 3–5 evidence-backed pain points |
| `evidence_urls`, `evidence_snippets` | Source URLs and excerpts used to derive labels |
| `reference_outreach` | Human-style reference cold email |
| `confidence_score`, `source_quality_score` | Pipeline confidence signals |
| `needs_human_review` | Flag for records that failed automated validation |

### Dataset quality (build-time validation)

| Stat | Value |
|------|-------|
| Companies | 100 |
| Passed automated validation | **89** |
| Needs human review | 11 |
| Avg confidence | 0.88 |
| Avg source quality | 0.97 |

### Build the dataset

```bash
# Requires OPENAI_API_KEY, FIRECRAWL_API_KEY, TAVILY_API_KEY in .env
make outboundbench

# Re-validate an existing CSV without rebuilding
make outboundbench-revalidate

# Quality report
make outboundbench-report
```

**Outputs:** `data/outboundbench_companies.csv`, `.jsonl`, `outboundbench_review_queue.csv`

---

## Agent Pipeline

OutboundOS runs a 6-agent LangGraph workflow per company:

```mermaid
flowchart TD
    START([Start]) --> research[Research Agent]
    research --> icp[ICP Agent]
    icp --> pain[Pain Point Agent]
    pain --> persona[Persona Agent]
    persona --> email[Email Generation]
    email --> reviewer[Reviewer Agent]
    reviewer -->|APPROVE| END([End])
    reviewer -->|REWRITE| rewrite[Rewrite Email]
    reviewer -->|RESEARCH| research
    rewrite --> reviewer
```

| Agent | Input | Output |
|-------|-------|--------|
| **Research** | Company name, website | `CompanySummary` (industry, description, evidence) |
| **ICP** | Company summary + `SellerProfile` (`config/seller_profile.json`) | ICP fit score (0–100) |
| **Pain Point** | Summary + hiring trends | Top pain points with messaging angles |
| **Persona** | Summary + ICP + `SellerProfile` | Buyer persona enum (`VP Sales`, `CTO`, etc.) |
| **Messaging** | Summary, pains, persona | Cold email + subject line |
| **Reviewer** | Full bundle | APPROVE / REWRITE / RESEARCH decision |

**Live mode** (default when `BENCHMARK_MODE=false` and API keys set): Firecrawl + Tavily web research, OpenAI structured outputs.

**Fallback mode** (`BENCHMARK_MODE=true` or missing keys): heuristic placeholders for CI and offline dev.

---

## Evaluation Metrics

All scores are in `[0, 1]` unless noted. Higher is better.

| Metric | What it measures | Notes |
|--------|------------------|-------|
| **Research accuracy** | Industry label match vs ground truth | Token overlap; exact match = 1.0 |
| **ICP accuracy** | ICP score vs target | `1 - |predicted - target| / 100` |
| **Pain point accuracy** | GT pain points covered by predictions | Per-pain token overlap threshold |
| **Persona accuracy** | Predicted buyer vs GT persona text | Role-family matching (sales, engineering, finance, etc.) |
| **Email quality** | Cold email vs GT pains + reference outreach | Weighted: company name 20%, pain overlap 40%, reference facts 25%, CTA 15% |
| **Reviewer agreement** | Reviewer decision vs expected decision | Expected derived from research + email quality |

### Honest framing

- **Strong today:** research, pain points — these reflect real web-grounded intelligence quality.
- **Improving:** email quality — composite metric replaced raw string similarity in July 2026; scores are not comparable to pre-v2 runs.
- **Known gap:** persona accuracy — agent outputs a coarse 8-value enum; ground truth uses rich natural-language personas (e.g. "Designers and Design Teams"). Family matching helps but does not fully close the gap.
- **Known benchmark/agent mismatch (new, July 2026):** ICP accuracy — see "The seller-profile fix" below. The agent now scores fit against a real, explicit seller profile; the benchmark's ground truth does not model any specific seller, so the two are answering subtly different questions.

### The seller-profile fix (why ICP accuracy dropped from 91% to 72%, on purpose)

Before July 11, 2026, the ICP agent scored companies with **zero information about who "we" are** — no target industries, no target buyer titles, nothing. It effectively measured "how impressive/well-documented is this company," not "is this company a good fit for a specific seller." That's a real product gap, not a benchmark artifact.

The fix added a `SellerProfile` (`app/schemas/seller_profile.py`, configured via `config/seller_profile.json`) — target industries, company size, buyer titles, disqualifiers — injected into both the ICP and Persona prompts. It defaults to describing OutboundOS itself (an outbound-automation platform targeting B2B SaaS/sales-tech/martech/RevOps-tooling companies).

**This is more correct behavior, and it made the ICP benchmark score go down, not up.** Here's why: OutboundBench's `icp_target` ground truth (`app/evaluation/outboundbench_loader.py::_estimate_icp_target`) is itself a generic heuristic — it rewards SaaS/fintech/devtools/cybersecurity industries broadly, with no concept of any specific seller. Once the agent started scoring fit against a real, narrower seller profile, it correctly scored companies outside that profile's target market (Stripe/fintech, cloud infra, devtools, cybersecurity) lower than the generic ground truth expects — because they genuinely are a worse fit for *this specific seller*, even though they're perfectly good companies in the abstract.

In other words: the agent and the benchmark are now answering two different implicit questions — "is this a good fit for OutboundOS specifically" (agent, after the fix) vs. "is this a generically impressive/tech-forward B2B company" (ground truth, unchanged). This is a benchmark methodology limitation, not a regression — a benchmark that wants to score seller-specific ICP fit would need ground truth that's *also* parameterized by a seller profile, which OutboundBench doesn't have.

Persona accuracy, by contrast, **improved slightly** (27% → 29%) after two rounds of prompt tuning — the first attempt over-indexed on the seller's target buyer titles and collapsed to picking "VP Sales" for nearly every company; the fix was to make company-specific signals (industry, product, tech stack) primary and the seller profile a secondary tie-breaker only. Worth knowing if asked "did you get it right the first try" — no, and here's the honest story of what broke and how it was diagnosed.

---

## Official Results

**Official baseline:** [`data/benchmark_results.json`](../data/benchmark_results.json)  
**Run ID:** `eval-20260711-145039` · **Generated:** 2026-07-11 · **n=100** · **Live agents**

| Metric | Score | Assessment |
|--------|-------|------------|
| Research accuracy | **98%** | Strong — industry extraction from live web evidence |
| Pain point accuracy | **87%** | Strong — evidence-backed pain identification |
| Email quality | **96%** | Strong — pain-grounded outreach with CTA (v2 composite metric) |
| Reviewer agreement | **98%** | Strong — reviewer decisions align with quality expectations |
| ICP accuracy | **72%** | **Dropped from 91%, on purpose** — now scored against a real seller profile instead of a generic heuristic; diverges from seller-agnostic ground truth (see above) |
| Persona accuracy | **29%** | **Gap** — coarse buyer enum vs natural-language GT personas (slightly improved from 27%) |

| Operations | Value |
|------------|-------|
| Avg latency | 50.9 s / company (up from 38.9s — this run hit intermittent Tavily search failures, gracefully absorbed but added retry latency) |
| Avg cost | $0.0090 / company |
| Concurrency | 2 |
| Total runtime | ~43 min |

### Historical baselines (context only — do not mix metric versions)

| Run ID | n | Metrics | Research | ICP | Pain | Persona | Email | Reviewer |
|--------|---|---------|----------|-----|------|---------|-------|----------|
| `eval-20260711-145039` | 100 | **v2 + seller profile (official)** | 0.98 | 0.72 | 0.87 | 0.29 | 0.96 | 0.98 |
| `eval-20260706-045418` | 100 | v2, no seller profile | 0.97 | 0.91 | 0.89 | 0.27 | 0.96 | 0.97 |
| `eval-20260706-040559` | 100 | v1 email/reviewer | 0.98 | 0.92 | 0.92 | 0.11 | 0.06 | 0.00 |
| `eval-20260706-041432` | 5 | v2 smoke test | 1.00 | 0.94 | 0.80 | 0.20 | 0.97 | 1.00 |

Use **`eval-20260711-145039`** for resume and README citations. The `eval-20260706-045418` row is kept for context — it's the last run *before* the ICP/Persona agents were made seller-profile-aware, which is why its ICP number is higher for reasons explained above, not because it's a "better" run.

---

## Run an Evaluation

```bash
# Full OutboundBench eval (100 companies, live agents)
make eval-outboundbench

# Smoke test (5 companies)
uv run python -m app.evaluation.run \
  --dataset data/outboundbench_companies.csv \
  --dataset-size 5 \
  --max-concurrency 2 \
  --quality-threshold 0.75

# Publish results as canonical baseline
uv run python -m app.evaluation.publish_benchmark \
  app/evaluation/history/<run-id>/summary.json
```

**Artifacts per run:** `app/evaluation/history/<run-id>/summary.json`, `records.csv`, charts.

---

## Resume-Safe Claims

Use these (backed by official n=100 baseline `eval-20260711-145039`):

- Built **OutboundBench** — 100-company evidence-grounded eval dataset (89/100 passed automated validation).
- Multi-agent **LangGraph** pipeline with live **Firecrawl/Tavily** research and structured **OpenAI** agents.
- **98% research accuracy** and **87% pain-point accuracy** on OutboundBench (n=100).
- **96% email quality** and **98% reviewer agreement** with evidence-grounded outreach generation.
- Evaluated at **~$0.009/company** and **~51s latency** with cost/token tracking.
- ICP and Persona scoring are grounded in an explicit, configurable **seller profile** (`config/seller_profile.json`) instead of scoring in a vacuum — a real gap that was found and fixed.

Avoid overstating:

- Persona targeting is the main bottleneck (**29%** accuracy) — cite as known gap, not a strength.
- ICP accuracy (**72%**) dropped from a prior 91% baseline *on purpose* after the seller-profile fix — cite the reason (benchmark ground truth is seller-agnostic; the agent is now correctly more seller-specific), don't just quote the number without context.
- Do not quote email/reviewer scores from pre-v2 metric runs (`eval-20260706-040559`).
