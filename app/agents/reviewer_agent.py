import json
import logging
from dataclasses import dataclass
from typing import cast

from app.agents.llm_outputs import ReviewerLLMOutput
from app.agents.prompts import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_TEMPLATE
from app.agents.runtime import get_agent_llm, live_agents_enabled
from app.schemas.reviewer import (
    ReviewerAgentInput,
    ReviewerCritique,
    ReviewerDecision,
    ReviewerScores,
)
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.agents.reviewer")


@dataclass(slots=True, frozen=True)
class ReviewerAgent:
    llm: StructuredLLMClient | None = None
    settings: Settings | None = None

    async def run(self, agent_input: ReviewerAgentInput) -> ReviewerCritique:
        resolved_settings = self.settings or get_settings()
        logger.info(
            "reviewer_agent_started | %s",
            {"company": agent_input.company_summary.company, "threshold": agent_input.threshold},
        )

        if live_agents_enabled(resolved_settings):
            critique = await self._run_live(agent_input, resolved_settings)
        else:
            critique = self._run_heuristic(agent_input)

        logger.info(
            "reviewer_agent_completed | %s",
            {"company": agent_input.company_summary.company, "decision": critique.decision},
        )
        return critique

    async def run_json(self, agent_input: ReviewerAgentInput) -> str:
        critique = await self.run(agent_input)
        return critique.model_dump_json()

    async def _run_live(
        self,
        agent_input: ReviewerAgentInput,
        settings: Settings,
    ) -> ReviewerCritique:
        summary = agent_input.company_summary
        known_facts = [
            summary.description,
            *summary.recent_news,
            *summary.evidence_snippets,
            *[point.description for point in agent_input.pain_points[:3]],
        ]
        llm = self.llm or get_agent_llm(settings)
        parsed = cast(
            ReviewerLLMOutput,
            await llm.parse(
                system_prompt=REVIEWER_SYSTEM_PROMPT,
                user_prompt=REVIEWER_USER_TEMPLATE.format(
                    threshold=agent_input.threshold,
                    company_name=summary.company,
                    persona=agent_input.persona_selection.persona,
                    pain_points=", ".join(
                        item.description for item in agent_input.pain_points[:3]
                    ),
                    cold_email=agent_input.message_bundle.cold_email,
                    known_facts="\n".join(f"- {fact}" for fact in known_facts if fact),
                ),
                schema=ReviewerLLMOutput,
            ),
        )
        scores = ReviewerScores(
            hallucinations=parsed.scores_hallucinations,
            generic_language=parsed.scores_generic_language,
            grammar=parsed.scores_grammar,
            unsupported_claims=parsed.scores_unsupported_claims,
            email_length=parsed.scores_email_length,
            personalization=parsed.scores_personalization,
            tone=parsed.scores_tone,
        )
        decision = _normalize_decision(parsed.decision)
        average = _average_score(scores)
        return ReviewerCritique(
            scores=scores,
            average_score=average,
            decision=decision,
            reasons=parsed.reasons,
            action_items=parsed.action_items,
        )

    @staticmethod
    def _run_heuristic(agent_input: ReviewerAgentInput) -> ReviewerCritique:
        text = agent_input.message_bundle.cold_email.lower()
        company = agent_input.company_summary.company.lower()
        personalization = 0.8 if company in text else 0.4
        scores = ReviewerScores(
            hallucinations=0.7,
            generic_language=0.75,
            grammar=0.9,
            unsupported_claims=0.7,
            email_length=0.85,
            personalization=personalization,
            tone=0.85,
        )
        average = _average_score(scores)
        decision: ReviewerDecision = "APPROVE" if average >= agent_input.threshold else "REWRITE"
        action_items = (
            ["No action required."]
            if decision == "APPROVE"
            else ["Improve personalization."]
        )
        return ReviewerCritique(
            scores=scores,
            average_score=average,
            decision=decision,
            reasons=["Heuristic review completed."],
            action_items=action_items,
        )


def _normalize_decision(decision: str) -> ReviewerDecision:
    normalized = decision.strip().upper()
    if normalized in {"APPROVE", "REWRITE", "RESEARCH"}:
        return cast(ReviewerDecision, normalized)
    return "REWRITE"


def _average_score(scores: ReviewerScores) -> float:
    values = [
        scores.hallucinations,
        scores.generic_language,
        scores.grammar,
        scores.unsupported_claims,
        scores.email_length,
        scores.personalization,
        scores.tone,
    ]
    return sum(values) / len(values)


def build_reviewer_payload_json(output: ReviewerCritique) -> str:
    return json.dumps(output.model_dump(), separators=(",", ":"))
