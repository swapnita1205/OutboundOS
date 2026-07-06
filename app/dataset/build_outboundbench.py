import argparse
import asyncio
import csv
import logging
from pathlib import Path
from typing import cast

from app.dataset.enrichers import enrich_company
from app.dataset.exporters import export_csv, export_jsonl, export_review_queue
from app.dataset.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_TEMPLATE,
    OUTREACH_SYSTEM_PROMPT,
    OUTREACH_USER_TEMPLATE,
)
from app.dataset.schemas import (
    EvidenceItem,
    LLMExtractionOutput,
    OutboundBenchRecord,
    OutreachValidation,
    ReferenceOutreachOutput,
    SeedCompany,
)
from app.dataset.validators import build_record, validate_outreach
from app.tools.llm_client import StructuredLLMClient
from app.utils.logging import configure_logging
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.dataset.builder")


def load_seed_companies(path: Path, limit: int | None = None) -> list[SeedCompany]:
    seeds: list[SeedCompany] = []
    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            seeds.append(
                SeedCompany(
                    company_name=row["company_name"].strip(),
                    website=row["website"].strip(),
                    category=row.get("category") or None,
                    notes=row.get("notes") or None,
                )
            )
            if limit is not None and len(seeds) >= limit:
                break
    return seeds


def _format_evidence_block(bundle_evidence: list[EvidenceItem]) -> str:
    lines: list[str] = []
    for item in bundle_evidence:
        lines.append(f"- URL: {item.url}\n  Type: {item.source_type}\n  Snippet: {item.snippet}")
    return "\n".join(lines)


async def _extract_fields(
    llm: StructuredLLMClient,
    seed: SeedCompany,
    evidence_block: str,
) -> LLMExtractionOutput:
    user_prompt = EXTRACTION_USER_TEMPLATE.format(
        company_name=seed.company_name,
        website=seed.website,
        evidence_block=evidence_block,
    )
    parsed = await llm.parse(
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=LLMExtractionOutput,
    )
    return cast(LLMExtractionOutput, parsed)


async def _generate_outreach(
    llm: StructuredLLMClient,
    seed: SeedCompany,
    extraction: LLMExtractionOutput,
    evidence_block: str,
    evidence_snippets: list[str],
) -> OutreachValidation:
    user_prompt = OUTREACH_USER_TEMPLATE.format(
        company_name=seed.company_name,
        industry=extraction.industry,
        target_persona=extraction.target_persona,
        pain_points=", ".join(item.description for item in extraction.pain_points),
        evidence_block=evidence_block,
    )
    parsed = await llm.parse(
        system_prompt=OUTREACH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=ReferenceOutreachOutput,
    )
    outreach_raw = cast(ReferenceOutreachOutput, parsed)
    return validate_outreach(
        outreach_raw.email_body,
        company_name=seed.company_name,
        pain_points=[item.description for item in extraction.pain_points],
        evidence_snippets=evidence_snippets,
    )


async def process_company(
    seed: SeedCompany,
    settings: Settings,
    llm: StructuredLLMClient,
) -> OutboundBenchRecord:
    bundle = await enrich_company(seed, settings)
    evidence_block = _format_evidence_block(bundle.evidence)
    extraction = await _extract_fields(llm, seed, evidence_block)
    outreach = await _generate_outreach(
        llm,
        seed,
        extraction,
        evidence_block,
        [item.snippet for item in bundle.evidence],
    )
    return build_record(bundle=bundle, extraction=extraction, outreach=outreach)


async def build_dataset(
    seeds: list[SeedCompany],
    *,
    max_concurrency: int = 4,
) -> list[OutboundBenchRecord]:
    settings = get_settings()
    llm = StructuredLLMClient(settings)
    semaphore = asyncio.Semaphore(max_concurrency)
    records: list[OutboundBenchRecord] = []

    async def _run(seed: SeedCompany) -> OutboundBenchRecord:
        async with semaphore:
            logger.info("processing_company", extra={"company": seed.company_name})
            return await process_company(seed, settings, llm)

    tasks = [_run(seed) for seed in seeds]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for seed, result in zip(seeds, results, strict=True):
        if isinstance(result, Exception):
            logger.error(
                "company_processing_failed",
                extra={"company": seed.company_name, "error": str(result)},
            )
            records.append(
                OutboundBenchRecord(
                    company_name=seed.company_name,
                    website=seed.website,
                    industry="unknown",
                    short_description="",
                    target_persona="unknown",
                    pain_points=[],
                    evidence_urls=[],
                    evidence_snippets=[],
                    reference_outreach="",
                    confidence_score=0.0,
                    needs_human_review=True,
                    source_quality_score=0.0,
                    generated_at=OutboundBenchRecord.now(),
                    validation_reasons=[f"processing_error:{result}"],
                )
            )
        else:
            records.append(cast(OutboundBenchRecord, result))
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build OutboundBench evaluation dataset")
    parser.add_argument("--input", type=str, default="app/dataset/seed_companies.csv")
    parser.add_argument("--output", type=str, default="data/outboundbench_companies.csv")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=4)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    configure_logging(get_settings().log_level)
    seeds = load_seed_companies(Path(args.input), limit=args.limit)
    records = await build_dataset(seeds, max_concurrency=args.concurrency)

    output_csv = Path(args.output)
    output_jsonl = output_csv.with_suffix(".jsonl")
    review_queue = output_csv.parent / "outboundbench_review_queue.csv"

    export_csv(records, output_csv)
    export_jsonl(records, output_jsonl)
    export_review_queue(records, review_queue)

    logger.info(
        "dataset_export_complete",
        extra={
            "rows": len(records),
            "csv": str(output_csv),
            "jsonl": str(output_jsonl),
            "review_queue": str(review_queue),
        },
    )
    print(f"Processed {len(records)} companies")
    print(f"CSV: {output_csv}")
    print(f"JSONL: {output_jsonl}")
    print(f"Review queue: {review_queue}")


if __name__ == "__main__":
    asyncio.run(main())
