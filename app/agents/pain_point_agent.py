import json
import logging
from dataclasses import dataclass
from typing import cast

from app.agents.llm_outputs import PainPointLLMOutput
from app.agents.prompts import PAIN_POINT_SYSTEM_PROMPT, PAIN_POINT_USER_TEMPLATE
from app.agents.runtime import get_agent_llm, live_agents_enabled
from app.schemas.company_summary import CompanySummary
from app.schemas.pain_points import PainPoint, PainPointAgentInput, PainPointOutput
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.agents.pain_points")


@dataclass(slots=True, frozen=True)
class PainPointAgent:
    llm: StructuredLLMClient | None = None
    settings: Settings | None = None

    async def run(self, agent_input: PainPointAgentInput) -> PainPointOutput:
        resolved_settings = self.settings or get_settings()
        summary = agent_input.company_summary
        logger.info("pain_point_agent_started | %s", {"company": summary.company})

        if live_agents_enabled(resolved_settings):
            result = await self._run_live(summary, agent_input.hiring_trends, resolved_settings)
        else:
            result = self._run_heuristic(summary, agent_input.hiring_trends)

        logger.info(
            "pain_point_agent_completed | %s",
            {"company": summary.company, "pain_points": len(result.top_pain_points)},
        )
        return result

    async def run_json(self, agent_input: PainPointAgentInput) -> str:
        output = await self.run(agent_input)
        return output.model_dump_json()

    async def _run_live(
        self,
        summary: CompanySummary,
        hiring_trends: list[str],
        settings: Settings,
    ) -> PainPointOutput:
        evidence_items = [
            f"URL: {url}\nSnippet: {snippet}"
            for url, snippet in zip(summary.evidence_urls, summary.evidence_snippets, strict=False)
        ]
        evidence_block = "\n".join(evidence_items) or "No evidence available."
        llm = self.llm or get_agent_llm(settings)
        parsed = cast(
            PainPointLLMOutput,
            await llm.parse(
                system_prompt=PAIN_POINT_SYSTEM_PROMPT,
                user_prompt=PAIN_POINT_USER_TEMPLATE.format(
                    company_name=summary.company,
                    industry=summary.industry,
                    description=summary.description,
                    hiring_trends=", ".join(hiring_trends) or "none",
                    evidence_block=evidence_block,
                ),
                schema=PainPointLLMOutput,
            ),
        )
        return _pad_to_five(parsed.top_pain_points, summary)

    @staticmethod
    def _run_heuristic(summary: CompanySummary, hiring_trends: list[str]) -> PainPointOutput:
        candidates: list[PainPoint] = []
        if summary.tech_stack:
            candidates.append(
                PainPoint(
                    description="Tool sprawl and platform complexity are slowing execution.",
                    evidence=[f"Tech stack: {', '.join(summary.tech_stack)}"],
                    confidence=0.82,
                    recommended_messaging_angle="Reduce manual handoffs across GTM tools.",
                )
            )
        if hiring_trends:
            candidates.append(
                PainPoint(
                    description="Hiring patterns suggest GTM bandwidth constraints.",
                    evidence=[hiring_trends[0]],
                    confidence=0.8,
                    recommended_messaging_angle="Automate research for lean teams.",
                )
            )
        if summary.recent_news:
            candidates.append(
                PainPoint(
                    description="Recent business changes create pipeline consistency pressure.",
                    evidence=[summary.recent_news[0]],
                    confidence=0.78,
                    recommended_messaging_angle="Tighten outbound iteration loops during change.",
                )
            )
        return _pad_to_five(candidates, summary)


def _pad_to_five(points: list[PainPoint], summary: CompanySummary) -> PainPointOutput:
    ranked = sorted(points, key=lambda item: item.confidence, reverse=True)[:5]
    while len(ranked) < 5:
        evidence = (
            [summary.description]
            if summary.description != "unknown"
            else [summary.company]
        )
        ranked.append(
            PainPoint(
                description="GTM execution risk due to incomplete operating signals.",
                evidence=evidence,
                confidence=0.5,
                recommended_messaging_angle="Start with fast discovery and progressive automation.",
            )
        )
    return PainPointOutput(top_pain_points=ranked[:5])


def build_pain_point_payload_json(output: PainPointOutput) -> str:
    return json.dumps(output.model_dump(), separators=(",", ":"))
