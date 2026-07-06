import json
import logging
from dataclasses import dataclass
from typing import cast

from app.agents.llm_outputs import PersonaLLMOutput
from app.agents.prompts import PERSONA_SYSTEM_PROMPT, PERSONA_USER_TEMPLATE
from app.agents.runtime import get_agent_llm, live_agents_enabled
from app.schemas.company_summary import CompanySummary
from app.schemas.persona import BuyerPersona, PersonaAgentInput, PersonaSelection
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.agents.persona")


@dataclass(slots=True, frozen=True)
class PersonaAgent:
    llm: StructuredLLMClient | None = None
    settings: Settings | None = None

    async def run(self, agent_input: PersonaAgentInput) -> PersonaSelection:
        resolved_settings = self.settings or get_settings()
        summary = agent_input.company_summary
        logger.info("persona_agent_started | %s", {"company": summary.company})

        if live_agents_enabled(resolved_settings):
            result = await self._run_live(summary, agent_input, resolved_settings)
        else:
            result = self._run_heuristic(summary, agent_input.icp_score)

        logger.info(
            "persona_agent_completed | %s",
            {
                "company": summary.company,
                "persona": result.persona,
                "confidence": result.confidence,
            },
        )
        return result

    async def run_json(self, agent_input: PersonaAgentInput) -> str:
        selection = await self.run(agent_input)
        return selection.model_dump_json()

    async def _run_live(
        self,
        summary: CompanySummary,
        agent_input: PersonaAgentInput,
        settings: Settings,
    ) -> PersonaSelection:
        llm = self.llm or get_agent_llm(settings)
        icp_score = agent_input.icp_score if agent_input.icp_score is not None else "unknown"
        parsed = cast(
            PersonaLLMOutput,
            await llm.parse(
                system_prompt=PERSONA_SYSTEM_PROMPT,
                user_prompt=PERSONA_USER_TEMPLATE.format(
                    company_summary=summary.model_dump_json(),
                    icp_score=icp_score,
                    ideal_persona="unknown",
                ),
                schema=PersonaLLMOutput,
            ),
        )
        return PersonaSelection(
            persona=parsed.persona,
            why=parsed.why,
            confidence=parsed.confidence,
        )

    @staticmethod
    def _run_heuristic(summary: CompanySummary, icp_score: float | None) -> PersonaSelection:
        persona = _choose_persona(summary)
        why = [f"Selected persona {persona} based on company signals."]
        confidence = 0.5 + (0.1 if summary.industry != "unknown" else 0.0)
        if icp_score is not None:
            confidence += (icp_score / 100.0) * 0.15
        return PersonaSelection(
            persona=persona,
            why=why,
            confidence=min(confidence, 1.0),
        )


def _choose_persona(summary: CompanySummary) -> BuyerPersona:
    if summary.ai_signals:
        return "Head of AI"
    if "saas" in summary.industry.lower():
        return "VP Engineering"
    if summary.tech_stack:
        return "CTO"
    return "VP Sales"


def build_persona_payload_json(selection: PersonaSelection) -> str:
    return json.dumps(selection.model_dump(), separators=(",", ":"))
