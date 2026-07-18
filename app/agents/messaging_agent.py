import json
import logging
from dataclasses import dataclass
from typing import cast

from app.agents.prompts import MESSAGING_SYSTEM_PROMPT, MESSAGING_USER_TEMPLATE
from app.agents.runtime import get_agent_llm, live_agents_enabled
from app.schemas.messaging import MessagingAgentInput, OutboundMessageBundle
from app.tools.email_tools import (
    DetectHallucinationsInput,
    ValidateEmailLengthInput,
    detect_hallucinations,
    validate_email_length,
)
from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings

logger = logging.getLogger("outboundos.agents.messaging")

MAX_WORDS = 150


@dataclass(slots=True, frozen=True)
class MessagingAgent:
    llm: StructuredLLMClient | None = None
    settings: Settings | None = None

    async def run(self, agent_input: MessagingAgentInput) -> OutboundMessageBundle:
        resolved_settings = self.settings or get_settings()
        company = agent_input.company_summary.company
        persona = agent_input.persona_selection.persona
        logger.info("messaging_agent_started | %s", {"company": company, "persona": persona})

        if live_agents_enabled(resolved_settings):
            bundle = await self._run_live(agent_input, resolved_settings)
        else:
            bundle = self._run_heuristic(agent_input)

        known_facts = _known_facts(agent_input)
        validated_bundle = await _validate_bundle(bundle, known_facts)
        logger.info("messaging_agent_completed | %s", {"company": company, "persona": persona})
        return validated_bundle

    async def run_json(self, agent_input: MessagingAgentInput) -> str:
        output = await self.run(agent_input)
        return output.model_dump_json()

    async def _run_live(
        self,
        agent_input: MessagingAgentInput,
        settings: Settings,
    ) -> OutboundMessageBundle:
        summary = agent_input.company_summary
        evidence_block = "\n".join(
            f"- {snippet}" for snippet in summary.evidence_snippets[:12]
        ) or summary.description
        llm = self.llm or get_agent_llm(settings)
        parsed = cast(
            OutboundMessageBundle,
            await llm.parse(
                system_prompt=MESSAGING_SYSTEM_PROMPT,
                user_prompt=MESSAGING_USER_TEMPLATE.format(
                    seller_profile=agent_input.seller_profile.model_dump_json(),
                    company_name=summary.company,
                    industry=summary.industry,
                    persona=agent_input.persona_selection.persona,
                    pain_points=", ".join(
                        item.description for item in agent_input.pain_points[:3]
                    ),
                    description=summary.description,
                    recent_news=", ".join(summary.recent_news[:3]) or "none",
                    evidence_block=evidence_block,
                ),
                schema=OutboundMessageBundle,
            ),
        )
        return parsed

    @staticmethod
    def _run_heuristic(agent_input: MessagingAgentInput) -> OutboundMessageBundle:
        company = agent_input.company_summary.company
        persona = agent_input.persona_selection.persona
        seller_name = agent_input.seller_profile.company_name
        primary_pain = (
            agent_input.pain_points[0].description
            if agent_input.pain_points
            else "limited outbound consistency"
        )
        cta = f"Open to a 15-minute chat next week to explore this with your {persona} team?"
        cold_email = (
            f"Hi there, I was reading about {company} and noticed {primary_pain.lower()}. "
            f"We built {seller_name} to help {persona} teams automate research "
            f"and personalized outreach. {cta}"
        )
        return OutboundMessageBundle(
            subject=f"{company}: quick idea",
            cold_email=_fit_words(cold_email),
            follow_up_1=_fit_words(f"Quick follow-up on {primary_pain.lower()}. {cta}"),
            follow_up_2=_fit_words(
                f"Last note — happy to share a workflow for {persona} teams. {cta}"
            ),
            linkedin_message=_fit_words(
                f"Hi, saw your work at {company}. We help with {primary_pain.lower()}. {cta}"
            ),
            call_to_action=cta,
        )


def _known_facts(agent_input: MessagingAgentInput) -> list[str]:
    summary = agent_input.company_summary
    facts = [summary.description, *summary.recent_news, *summary.evidence_snippets]
    facts.extend(item.description for item in agent_input.pain_points[:3])
    return [fact for fact in facts if fact]


async def _validate_bundle(
    bundle: OutboundMessageBundle,
    known_facts: list[str],
) -> OutboundMessageBundle:
    cold_email = await _validate_text_quality(bundle.cold_email, known_facts)
    follow_up_1 = await _validate_text_quality(bundle.follow_up_1, known_facts)
    follow_up_2 = await _validate_text_quality(bundle.follow_up_2, known_facts)
    linkedin_message = await _validate_text_quality(bundle.linkedin_message, known_facts)
    return OutboundMessageBundle(
        subject=bundle.subject,
        cold_email=cold_email,
        follow_up_1=follow_up_1,
        follow_up_2=follow_up_2,
        linkedin_message=linkedin_message,
        call_to_action=bundle.call_to_action,
    )


async def _validate_text_quality(text: str, known_facts: list[str]) -> str:
    length_result = await validate_email_length(
        ValidateEmailLengthInput(email_body=text, min_chars=20, max_chars=1000)
    )
    hallucination_result = await detect_hallucinations(
        DetectHallucinationsInput(email_body=text, known_facts=known_facts),
    )
    refined = text
    if not length_result.is_valid:
        refined = _fit_words(text)
    if hallucination_result.hallucination_detected:
        refined = _replace_claimy_phrases(refined)
    return _fit_words(refined)


def _replace_claimy_phrases(text: str) -> str:
    replacements = {
        "you are likely": "you may be",
        "will": "can",
        "definitely": "likely",
        "guarantee": "aim to",
    }
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    return updated


def _fit_words(text: str, max_words: int = MAX_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def build_messaging_payload_json(output: OutboundMessageBundle) -> str:
    return json.dumps(output.model_dump(), separators=(",", ":"))
