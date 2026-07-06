from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class AgentDefinition:
    name: str
    description: str


AGENT_REGISTRY: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        name="icp_agent",
        description="Scores ICP fit from CompanySummary and returns structured ICPScore JSON.",
    ),
    AgentDefinition(
        name="messaging_agent",
        description="Generates persona-aware outbound messaging bundle with follow-ups.",
    ),
    AgentDefinition(
        name="pain_point_agent",
        description="Predicts top business pain points from company and market signals.",
    ),
    AgentDefinition(
        name="persona_agent",
        description="Selects the best buyer persona with rationale and confidence.",
    ),
    AgentDefinition(
        name="research_agent",
        description="Collects company research and returns structured company summary JSON.",
    ),
    AgentDefinition(
        name="reviewer_agent",
        description="Critiques outbound messaging and returns APPROVE, REWRITE, or RESEARCH.",
    ),
)
