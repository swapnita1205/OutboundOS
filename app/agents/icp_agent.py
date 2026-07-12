import json
import logging
from dataclasses import dataclass
from typing import cast

from app.agents.llm_outputs import AgentICPScore
from app.agents.prompts import ICP_SYSTEM_PROMPT, ICP_USER_TEMPLATE
from app.agents.runtime import get_agent_llm, live_agents_enabled
from app.schemas.company_summary import CompanySummary
from app.schemas.icp_score import ICPAgentInput, ICPScore
from app.schemas.seller_profile import SellerProfile
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.agents.icp")


@dataclass(slots=True, frozen=True)
class ICPAgent:
    llm: StructuredLLMClient | None = None
    settings: Settings | None = None

    async def run(self, agent_input: ICPAgentInput) -> ICPScore:
        resolved_settings = self.settings or get_settings()
        summary = agent_input.company_summary
        seller_profile = agent_input.seller_profile
        logger.info(
            "icp_agent_started | %s",
            {"company": summary.company, "seller": seller_profile.company_name},
        )

        if live_agents_enabled(resolved_settings):
            result = await self._run_live(summary, seller_profile, resolved_settings)
        else:
            result = self._run_heuristic(summary, seller_profile)

        logger.info(
            "icp_agent_completed | %s",
            {"company": summary.company, "score": result.score, "confidence": result.confidence},
        )
        return result

    async def run_json(self, agent_input: ICPAgentInput) -> str:
        score = await self.run(agent_input)
        return score.model_dump_json()

    async def _run_live(
        self,
        summary: CompanySummary,
        seller_profile: SellerProfile,
        settings: Settings,
    ) -> ICPScore:
        llm = self.llm or get_agent_llm(settings)
        return cast(
            AgentICPScore,
            await llm.parse(
                system_prompt=ICP_SYSTEM_PROMPT,
                user_prompt=ICP_USER_TEMPLATE.format(
                    seller_profile=seller_profile.model_dump_json(),
                    company_summary=summary.model_dump_json(),
                ),
                schema=ICPScore,
            ),
        )

    @staticmethod
    def _run_heuristic(summary: CompanySummary, seller_profile: SellerProfile) -> ICPScore:
        industry_lower = summary.industry.lower()
        target_industries_lower = [target.lower() for target in seller_profile.target_industries]
        industry_matches = industry_lower != "unknown" and any(
            target in industry_lower or industry_lower in target
            for target in target_industries_lower
        )

        score = 30.0
        reasons: list[str] = []
        if industry_matches:
            score += 25.0
            reasons.append(
                f"Industry ({summary.industry}) aligns with seller's target industries "
                f"({', '.join(seller_profile.target_industries)})."
            )
        elif summary.industry != "unknown":
            score += 5.0
            reasons.append(
                f"Industry ({summary.industry}) identified but outside seller's stated "
                "target industries."
            )
        if summary.tech_stack:
            score += 10.0
            reasons.append("Tech stack signals available")
        if summary.ai_signals:
            score += 10.0
            reasons.append("AI-related initiatives detected")
        if summary.recent_news:
            score += 10.0
            reasons.append("Recent market activity present")
        if summary.funding != "unknown":
            score += 5.0
            reasons.append("Funding data available")

        risk_flags: list[str] = []
        if summary.industry == "unknown":
            risk_flags.append("Industry is unknown")
        elif not industry_matches:
            risk_flags.append("Industry does not clearly match seller's target industries")
        if not summary.recent_news:
            risk_flags.append("No recent news identified")

        ideal_persona = (
            seller_profile.target_buyer_titles[0]
            if seller_profile.target_buyer_titles
            else "VP Engineering"
        )
        confidence = 0.55 if reasons else 0.35
        return ICPScore(
            score=min(score, 100.0),
            reasons=reasons or ["Limited company signals"],
            ideal_persona=ideal_persona,
            risk_flags=risk_flags,
            confidence=confidence,
        )


def build_icp_payload_json(score: ICPScore) -> str:
    return json.dumps(score.model_dump(), separators=(",", ":"))
