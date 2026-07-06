import pytest

from app.dataset.build_outboundbench import _extract_fields
from app.dataset.schemas import LLMExtractionOutput, PainPointExtraction, SeedCompany
from app.tools.llm_client import StructuredLLMClient


class _FakeLLM(StructuredLLMClient):
    def __init__(self) -> None:
        pass

    async def parse(self, *, system_prompt: str, user_prompt: str, schema: type) -> object:
        return LLMExtractionOutput(
            industry="saas",
            short_description="Cloud platform for revenue teams.",
            target_persona="VP Sales",
            pain_points=[
                PainPointExtraction(
                    description="Manual research slows outbound",
                    evidence_urls=["https://acme.com/about"],
                    evidence_snippets=["Teams spend hours on account research"],
                )
            ],
            confidence_score=0.88,
            persona_confidence=0.82,
        )


@pytest.mark.asyncio
async def test_mocked_llm_extraction() -> None:
    seed = SeedCompany(company_name="Acme", website="https://acme.com")
    extraction = await _extract_fields(_FakeLLM(), seed, "evidence")
    assert extraction.industry == "saas"
    assert extraction.target_persona == "VP Sales"
