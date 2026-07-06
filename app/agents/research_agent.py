import json
import logging
from dataclasses import dataclass
from typing import cast

from app.agents.llm_outputs import ResearchLLMOutput
from app.agents.prompts import RESEARCH_SYSTEM_PROMPT, RESEARCH_USER_TEMPLATE
from app.agents.runtime import get_agent_llm, live_agents_enabled
from app.schemas.company_summary import CompanySummary, ResearchAgentInput
from app.tools.company_evidence import collect_company_evidence, format_evidence_block
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.agents.research")

DEFAULT_VALUE = "unknown"


@dataclass(slots=True, frozen=True)
class ResearchAgent:
    llm: StructuredLLMClient | None = None
    settings: Settings | None = None

    async def run(self, agent_input: ResearchAgentInput) -> CompanySummary:
        resolved_settings = self.settings or get_settings()
        logger.info(
            "research_agent_started | %s",
            {"company_name": agent_input.company_name, "website": str(agent_input.website)},
        )

        if live_agents_enabled(resolved_settings):
            summary = await self._run_live(agent_input, resolved_settings)
        else:
            summary = self._run_heuristic(agent_input)

        logger.info(
            "research_agent_completed | %s",
            {
                "company_name": summary.company,
                "industry": summary.industry,
                "news_count": len(summary.recent_news),
            },
        )
        return summary

    async def run_json(self, agent_input: ResearchAgentInput) -> str:
        summary = await self.run(agent_input)
        return summary.model_dump_json()

    async def _run_live(
        self,
        agent_input: ResearchAgentInput,
        settings: Settings,
    ) -> CompanySummary:
        bundle = await collect_company_evidence(
            agent_input.company_name,
            str(agent_input.website),
            settings,
        )
        evidence_block = format_evidence_block(bundle.evidence)
        llm = self.llm or get_agent_llm(settings)
        parsed = cast(
            ResearchLLMOutput,
            await llm.parse(
                system_prompt=RESEARCH_SYSTEM_PROMPT,
                user_prompt=RESEARCH_USER_TEMPLATE.format(
                    company_name=agent_input.company_name,
                    website=bundle.website,
                    evidence_block=evidence_block or "No evidence collected.",
                ),
                schema=ResearchLLMOutput,
            ),
        )
        return CompanySummary(
            company=agent_input.company_name,
            industry=parsed.industry or DEFAULT_VALUE,
            description=parsed.description or DEFAULT_VALUE,
            employees=parsed.employees or DEFAULT_VALUE,
            recent_news=parsed.recent_news,
            products=parsed.products,
            customers=parsed.customers,
            funding=parsed.funding or DEFAULT_VALUE,
            tech_stack=parsed.tech_stack,
            ai_signals=parsed.ai_signals,
            evidence_urls=[item.url for item in bundle.evidence],
            evidence_snippets=[item.snippet for item in bundle.evidence if item.snippet],
        )

    @staticmethod
    def _run_heuristic(agent_input: ResearchAgentInput) -> CompanySummary:
        return CompanySummary(
            company=agent_input.company_name,
            industry=DEFAULT_VALUE,
            description=f"Summary prepared for {agent_input.company_name}",
            employees=DEFAULT_VALUE,
            recent_news=[f"Recent update about {agent_input.company_name}"],
            products=[],
            customers=[],
            funding=DEFAULT_VALUE,
            tech_stack=[],
            ai_signals=[],
            evidence_urls=[str(agent_input.website)],
            evidence_snippets=[f"Website reference for {agent_input.company_name}"],
        )


def build_research_payload_json(summary: CompanySummary) -> str:
    return json.dumps(summary.model_dump(), separators=(",", ":"))
