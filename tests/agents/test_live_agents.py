import pytest
from pydantic import HttpUrl

from app.agents.icp_agent import ICPAgent
from app.agents.llm_outputs import ResearchLLMOutput
from app.agents.research_agent import ResearchAgent
from app.agents.runtime import live_agents_enabled
from app.schemas.company_summary import ResearchAgentInput
from app.schemas.icp_score import ICPAgentInput, ICPScore
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings


class _FakeLLM(StructuredLLMClient):
    def __init__(self) -> None:
        pass

    async def parse(self, *, system_prompt: str, user_prompt: str, schema: type) -> object:
        if schema is ResearchLLMOutput:
            return ResearchLLMOutput(
                industry="Financial Technology",
                description="Payment infrastructure for global businesses.",
                recent_news=["Stripe expands payment platform"],
                tech_stack=["python"],
                ai_signals=["automation"],
            )
        if schema is ICPScore:
            return ICPScore(
                score=82.0,
                reasons=["Strong SaaS fit"],
                ideal_persona="VP Sales",
                risk_flags=[],
                confidence=0.86,
            )
        raise AssertionError(f"Unexpected schema: {schema}")


@pytest.mark.asyncio
async def test_research_agent_heuristic_without_api_key() -> None:
    settings = Settings(openai_api_key=None, benchmark_mode=False)
    agent = ResearchAgent(settings=settings)
    summary = await agent.run(
        ResearchAgentInput(company_name="Stripe", website=HttpUrl("https://stripe.com"))
    )
    assert summary.company == "Stripe"
    assert live_agents_enabled(settings) is False


@pytest.mark.asyncio
async def test_research_agent_live_with_fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(openai_api_key="test-key", benchmark_mode=False)

    async def _fake_collect(company_name: str, website: str, _settings: Settings) -> object:
        from app.tools.company_evidence import CompanyEvidence

        return CompanyEvidence(
            company_name=company_name,
            website=website,
            homepage_scraped=True,
            evidence=[],
            scrape_errors=[],
        )

    monkeypatch.setattr(
        "app.agents.research_agent.collect_company_evidence",
        _fake_collect,
    )
    agent = ResearchAgent(llm=_FakeLLM(), settings=settings)
    summary = await agent.run(
        ResearchAgentInput(company_name="Stripe", website=HttpUrl("https://stripe.com"))
    )
    assert summary.industry == "Financial Technology"
    assert "payment" in summary.description.lower()


@pytest.mark.asyncio
async def test_icp_agent_live_with_fake_llm() -> None:
    from app.schemas.company_summary import CompanySummary

    settings = Settings(openai_api_key="test-key", benchmark_mode=False)
    agent = ICPAgent(llm=_FakeLLM(), settings=settings)
    score = await agent.run(
        ICPAgentInput(
            company_summary=CompanySummary(
                company="Stripe",
                industry="fintech",
                description="payments",
                employees="unknown",
                recent_news=[],
                products=[],
                customers=[],
                funding="unknown",
                tech_stack=[],
                ai_signals=[],
            )
        )
    )
    assert score.score == 82.0
