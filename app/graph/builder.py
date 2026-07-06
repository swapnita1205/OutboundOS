from time import perf_counter
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from app.agents.icp_agent import ICPAgent
from app.agents.messaging_agent import MessagingAgent
from app.agents.pain_point_agent import PainPointAgent
from app.agents.persona_agent import PersonaAgent
from app.agents.research_agent import ResearchAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.graph.state import OutboundWorkflowState, WorkflowDecision
from app.schemas.company_summary import ResearchAgentInput
from app.schemas.icp_score import ICPAgentInput
from app.schemas.messaging import MessagingAgentInput
from app.schemas.pain_points import PainPointAgentInput
from app.schemas.persona import PersonaAgentInput
from app.schemas.reviewer import ReviewerAgentInput

research_agent = ResearchAgent()
icp_agent = ICPAgent()
pain_point_agent = PainPointAgent()
persona_agent = PersonaAgent()
messaging_agent = MessagingAgent()
reviewer_agent = ReviewerAgent()


async def research_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    summary = await research_agent.run(
        ResearchAgentInput(company_name=updated["company_name"], website=updated["website"]),
    )
    updated["company_summary"] = summary
    _append_trace(updated, "research", "Collected and structured company intelligence.")
    _track_metrics(updated, start, summary.model_dump_json())
    return updated


async def icp_analysis_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    summary = updated["company_summary"]
    icp = await icp_agent.run(ICPAgentInput(company_summary=summary))
    updated["icp_score"] = icp
    _append_trace(updated, "icp", f"ICP score assigned at {icp.score}.")
    _track_metrics(updated, start, icp.model_dump_json())
    return updated


async def pain_point_analysis_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    pain_points = await pain_point_agent.run(
        PainPointAgentInput(
            company_summary=updated["company_summary"],
            hiring_trends=updated["hiring_trends"],
        )
    )
    updated["pain_points"] = pain_points
    _append_trace(updated, "pain_points", "Predicted top pain points and messaging angles.")
    _track_metrics(updated, start, pain_points.model_dump_json())
    return updated


async def persona_selection_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    persona = await persona_agent.run(
        PersonaAgentInput(
            company_summary=updated["company_summary"],
            icp_score=updated["icp_score"].score,
        )
    )
    updated["persona_selection"] = persona
    _append_trace(updated, "persona", f"Selected buyer persona {persona.persona}.")
    _track_metrics(updated, start, persona.model_dump_json())
    return updated


async def email_generation_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    bundle = await messaging_agent.run(
        MessagingAgentInput(
            company_summary=updated["company_summary"],
            pain_points=updated["pain_points"].top_pain_points,
            persona_selection=updated["persona_selection"],
        )
    )
    updated["message_bundle"] = bundle
    _append_trace(updated, "email_generation", "Generated initial outbound messaging bundle.")
    _track_metrics(updated, start, bundle.model_dump_json())
    return updated


async def rewrite_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    bundle = await messaging_agent.run(
        MessagingAgentInput(
            company_summary=updated["company_summary"],
            pain_points=updated["pain_points"].top_pain_points,
            persona_selection=updated["persona_selection"],
        )
    )
    updated["message_bundle"] = bundle
    _append_trace(updated, "rewrite", "Re-generated messaging bundle after review failure.")
    _track_metrics(updated, start, bundle.model_dump_json())
    return updated


async def reviewer_node(state: OutboundWorkflowState) -> OutboundWorkflowState:
    updated = cast(OutboundWorkflowState, dict(state))
    start = perf_counter()

    critique = await reviewer_agent.run(
        ReviewerAgentInput(
            message_bundle=updated["message_bundle"],
            company_summary=updated["company_summary"],
            pain_points=updated["pain_points"].top_pain_points,
            persona_selection=updated["persona_selection"],
            threshold=updated["quality_threshold"],
        )
    )
    updated["reviewer_critique"] = critique
    updated["quality_score"] = critique.average_score
    updated["iteration_count"] = updated["iteration_count"] + 1

    if critique.decision == "APPROVE":
        updated["reviewer_decision"] = "APPROVE"
    else:
        if updated["review_fail_count"] == 0:
            updated["reviewer_decision"] = "REWRITE"
        else:
            updated["reviewer_decision"] = "RESEARCH"
        updated["review_fail_count"] = updated["review_fail_count"] + 1

    _append_trace(
        updated,
        "review",
        f"Reviewer decision {critique.decision} at quality {critique.average_score:.2f}.",
    )
    _track_metrics(updated, start, critique.model_dump_json())
    return updated


def reviewer_router(state: OutboundWorkflowState) -> str:
    if state["reviewer_decision"] == "APPROVE":
        return "end"
    if state["iteration_count"] >= state["max_iterations"]:
        return "end"

    decision: WorkflowDecision = state["reviewer_decision"]
    if decision == "REWRITE":
        return "rewrite"
    if decision == "RESEARCH":
        return "research"
    return "end"


def persona_router(state: OutboundWorkflowState) -> str:
    if state["review_fail_count"] > 0 and state["reviewer_decision"] == "RESEARCH":
        return "rewrite"
    return "email_generation"


def build_graph() -> Any:
    workflow = StateGraph(OutboundWorkflowState)

    workflow.add_node("research", research_node)
    workflow.add_node("icp_analysis", icp_analysis_node)
    workflow.add_node("pain_point_analysis", pain_point_analysis_node)
    workflow.add_node("persona_selection", persona_selection_node)
    workflow.add_node("email_generation", email_generation_node)
    workflow.add_node("rewrite", rewrite_node)
    workflow.add_node("reviewer", reviewer_node)

    workflow.add_edge(START, "research")
    workflow.add_edge("research", "icp_analysis")
    workflow.add_edge("icp_analysis", "pain_point_analysis")
    workflow.add_edge("pain_point_analysis", "persona_selection")
    workflow.add_edge("email_generation", "reviewer")
    workflow.add_edge("rewrite", "reviewer")
    workflow.add_conditional_edges(
        "persona_selection",
        persona_router,
        {"rewrite": "rewrite", "email_generation": "email_generation"},
    )

    workflow.add_conditional_edges(
        "reviewer",
        reviewer_router,
        {"research": "research", "rewrite": "rewrite", "end": END},
    )

    return workflow.compile()


def get_graph_visualization() -> str:
    compiled_graph = build_graph()
    return cast(str, compiled_graph.get_graph().draw_mermaid())


def _append_trace(state: OutboundWorkflowState, stage: str, detail: str) -> None:
    trace = state.get("reasoning_trace", [])
    trace.append(f"{stage}: {detail}")
    state["reasoning_trace"] = trace


def _track_metrics(state: OutboundWorkflowState, started_at: float, payload: str) -> None:
    elapsed_ms = (perf_counter() - started_at) * 1000
    tokens = max(1, len(payload.split()) * 2)
    cost = tokens * 0.0000025
    state["total_latency_ms"] = state.get("total_latency_ms", 0.0) + elapsed_ms
    state["total_token_usage"] = state.get("total_token_usage", 0) + tokens
    state["total_cost_usd"] = state.get("total_cost_usd", 0.0) + cost
