import csv
import json
import re
from pathlib import Path

from pydantic import HttpUrl

from app.evaluation.models import EvaluationSample, GroundTruth


def _parse_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise TypeError("Expected JSON list for string list field")
        return [str(item) for item in parsed]
    raise TypeError(f"Unsupported list field type: {type(value)!r}")


def load_outboundbench_dataset(
    path: Path,
    *,
    limit: int | None = None,
) -> list[EvaluationSample]:
    records = _load_rows(path)
    if limit is not None:
        records = records[:limit]

    samples: list[EvaluationSample] = []
    for row in records:
        persona = str(row["target_persona"])
        industry = str(row["industry"])
        pain_points = _parse_string_list(row["pain_points"])
        samples.append(
            EvaluationSample(
                company_name=str(row["company_name"]),
                website=HttpUrl(str(row["website"])),
                hiring_trends=_derive_hiring_trends(row),
                ground_truth=GroundTruth(
                    industry=industry,
                    persona=persona,
                    pain_points=pain_points,
                    reference_outreach=str(row["reference_outreach"]),
                    icp_target=_estimate_icp_target(industry, persona),
                ),
            )
        )
    return samples


def _load_rows(path: Path) -> list[dict[str, object]]:
    if path.suffix == ".jsonl":
        rows: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                rows.append(json.loads(line))
        return rows

    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _derive_hiring_trends(row: dict[str, object]) -> list[str]:
    snippets = _parse_string_list(row.get("evidence_snippets", "[]"))
    careers_snippets = [snippet for snippet in snippets if _looks_like_hiring(snippet)]
    if careers_snippets:
        return [careers_snippets[0][:160]]
    return [f"Hiring and growth signals for {row['company_name']}"]


def _looks_like_hiring(snippet: str) -> bool:
    lowered = snippet.lower()
    return any(token in lowered for token in ("hiring", "careers", "jobs", "open roles"))


def _estimate_icp_target(industry: str, persona: str) -> float:
    score = 65.0
    industry_tokens = _tokenize(industry)
    persona_tokens = _tokenize(persona)

    if industry_tokens & {"saas", "software", "fintech", "devtools", "cybersecurity"}:
        score += 10.0
    if persona_tokens & {
        "cto",
        "engineering",
        "devops",
        "security",
        "revenue",
        "sales",
        "marketing",
    }:
        score += 10.0
    if "enterprise" in industry.lower() or "enterprise" in persona.lower():
        score += 5.0
    return min(100.0, score)


def _tokenize(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}
