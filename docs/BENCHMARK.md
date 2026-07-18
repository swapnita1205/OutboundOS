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
| `pain_points` | Evidence-backed pain points |
| `evidence_urls`, `evidence_snippets` | Source URLs and excerpts the labels were derived from |
| `reference_outreach` | Reference cold email |

### How the ground truth is built

- **Evidence** is collected per company via live web scraping — Firecrawl page scrapes (homepage, about, careers, blog, docs, pricing, customers) plus Tavily search — and classified by source type (website, blog, docs, careers, news).
- **Labels** (industry, description, persona, pain points, reference outreach) are **authored by hand** from that evidence in a labeling worksheet.
- Because the labels are human judgment rather than model output, the benchmark measures **agent quality against an independent source of truth**, not agreement between two models using similar vocabulary.

**Files:** `data/human_ground_truth/outboundbench_human.csv` (dataset), `data/human_ground_truth/worksheet.csv` (evidence + human labels).

### Compile / report

```bash
# Compile the filled-in worksheet into the dataset CSV
make human-ground-truth

# Dataset quality/distribution report
make outboundbench-report
```

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
| **Pain point accuracy** | GT pain points covered by predictions | Per GT pain: **max** of token overlap and embedding-cosine paraphrase match |
| **Persona accuracy** | Predicted buyer vs GT persona text | Role-family matching (sales, engineering, finance, etc.) |
| **Email quality** | Cold email vs GT pains + reference outreach | Weighted: company name 20%, pain coverage 40%, reference facts 25%, CTA 15% |
| **Reviewer agreement** | Reviewer decision vs expected decision | Expected derived from research + email quality |

### Semantic (paraphrase-aware) scoring

Pain-point and email pain-coverage scoring combine two signals and take the better of the two per ground-truth pain:

1. **Token overlap** — fast exact/near-exact wording match (retained as a floor).
2. **Embedding cosine** — each ground-truth pain is embedded (`text-embedding-3-small`) and compared to the agent's pain points / email sentences by cosine similarity, mapped through a tolerance band: **≥ 0.60 cosine = full credit, ≤ 0.35 = zero, linear in between**.

Why: pure token overlap scores paraphrases as total misses — e.g. "knowledge scattered across disconnected tools" vs "teams struggle with fragmented information" share almost no tokens but mean the same thing. Against human-authored ground truth (which uses different vocabulary than any LLM), that weakness dominates the score. The band was calibrated against real pairs — genuine paraphrases land at ~0.59–0.61 cosine, unrelated pains at ~0.30 — so the threshold cleanly separates them. When no OpenAI key is available (CI/offline) or the embeddings call fails mid-run, scoring degrades gracefully to pure token overlap.

This is neither Jaccard (intersection/union) nor a single hard cutoff — it's token overlap as an exact-wording floor plus embedding cosine with a calibrated tolerance band for paraphrases.

### Honest framing

- **Strong:** research, email quality, reviewer agreement — real web-grounded intelligence and structurally sound, pain-grounded outreach.
- **Solid:** pain points and ICP — pain points are paraphrase-aware against independent human labels; ICP is anchored to a real seller profile.
- **Known gap:** persona accuracy — the agent outputs a coarse 8-value enum; ground truth uses rich natural-language personas (e.g. "Designers and Design Teams"). Family matching helps but does not fully close the gap.
- **Known benchmark/agent mismatch:** ICP accuracy — see "Seller-profile-aware ICP/Persona" below. The agent scores fit against a real, explicit seller profile; the benchmark's ICP target does not model any specific seller, so the two answer subtly different questions.

### Seller-profile-aware ICP/Persona

The ICP and Persona agents score/select relative to an explicit `SellerProfile` (`app/schemas/seller_profile.py`, configured via `config/seller_profile.json`) — target industries, company size, buyer titles, disqualifiers — injected into both prompts. It defaults to describing OutboundOS itself (an outbound-automation platform targeting B2B SaaS / sales-tech / martech / RevOps-tooling companies).

This is the correct behavior for a real deployment, but it creates a deliberate mismatch with the benchmark: OutboundBench's `icp_target` (`app/evaluation/outboundbench_loader.py::_estimate_icp_target`) is a generic heuristic that rewards SaaS/fintech/devtools/cybersecurity broadly, with no concept of a specific seller. A genuinely seller-anchored score will diverge from it for companies outside that seller's target market — not because the agent is wrong, but because the two are answering different implicit questions. Closing this would require ground truth that is *also* parameterized by a seller profile.

Persona selection needed two rounds of prompt tuning to avoid collapsing onto a single dominant answer once seller context was added (first over-indexing on the seller's target buyer titles → nearly always "VP Sales"; then onto "Head of AI" because AI-feature mentions are near-universal in 2026 marketing copy). The fix was to make company-specific signals (industry, product, tech stack) primary and the seller profile a secondary tie-breaker.

---

## Official Results

**Official baseline:** [`data/benchmark_results.json`](../data/benchmark_results.json)  
**Run ID:** `eval-20260718-232055` · **Generated:** 2026-07-18 · **n=100** · **Live agents**

| Metric | Score | Assessment |
|--------|-------|------------|
| Research accuracy | **96%** | Strong — industry extraction from live web evidence |
| Email quality | **83%** | Strong — pain-grounded outreach with CTA |
| ICP accuracy | **82%** | Solid — scored against a real seller profile (see note above) |
| Reviewer agreement | **88%** | Strong — reviewer decisions align with quality expectations |
| Pain point accuracy | **70%** | Solid — semantic paraphrase-aware match vs human labels |
| Persona accuracy | **49%** | **Gap** — coarse buyer enum vs natural-language GT personas |

| Operations | Value |
|------------|-------|
| Avg latency | ~35 s / company |
| Avg cost | ~$0.011 / company |
| Concurrency | 2 |
| Total runtime | ~30 min |

### Metric-methodology comparison (same human-authored dataset, n=100)

| Run ID | Pain scoring | Pain | Email | Notes |
|--------|--------------|------|-------|-------|
| **`eval-20260718-232055`** | **token + semantic (official)** | **0.70** | **0.83** | Paraphrase-aware scoring |
| `eval-20260718-224055` | token only | 0.59 | 0.76 | Same dataset, before the semantic fix |

The jump in pain-point (0.59 → 0.70) and email (0.76 → 0.83) comes entirely from the metric change — the agent didn't change between these runs. Token-only scoring was penalizing correct pain points that were phrased differently from the human labels; the semantic band gives paraphrases credit. Both runs use the same human-authored ground truth.

---

## Run an Evaluation

```bash
# Full OutboundBench eval (100 companies, live agents)
make eval-outboundbench

# Smoke test (5 companies)
uv run python -m app.evaluation.run \
  --dataset data/human_ground_truth/outboundbench_human.csv \
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

Use these (backed by official n=100 baseline `eval-20260718-232055`):

- Built **OutboundBench** — a 100-company evidence-grounded eval dataset with **human-authored** ground truth labeled from real web evidence.
- Multi-agent **LangGraph** pipeline with live **Firecrawl/Tavily** research and structured **OpenAI** agents.
- **96% research accuracy** and **70% pain-point accuracy** (paraphrase-aware scoring) on OutboundBench (n=100).
- **83% email quality** and **88% reviewer agreement** with evidence-grounded outreach generation.
- Designed a **semantic evaluation metric** (embedding-cosine tolerance band + token-overlap floor) that measures meaning, not vocabulary — verified it recovered credit for correct paraphrases the token-only metric was scoring as zero.
- Evaluated at **~$0.011/company** and **~35s latency** with cost/token tracking.
- ICP and Persona scoring are grounded in an explicit, configurable **seller profile** (`config/seller_profile.json`) instead of scoring in a vacuum.

Avoid overstating:

- Persona targeting is the main bottleneck (**49%** accuracy) — cite as known gap, not a strength.
- ICP accuracy (**82%**) reflects scoring against a real seller profile that the benchmark's generic ground truth doesn't model — cite the mismatch, don't imply the two measure the same thing.
