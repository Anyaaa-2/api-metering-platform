"""
The usage advisor as a LangGraph state machine.

    observe ──► analyze ──► validate ──┬──► analyze   (rejected: retry with the validator's errors)
                  ▲                    ├──► analyze   (accepted: next client)
                  └────────────────────┘
                                       └──► END       (all clients done)

- observe:  fetch usage for every client and compute signals (no LLM)
- analyze:  ask the LLM for a structured recommendation for one client
- validate: check it against guardrails; on failure, loop back with feedback

The advisor is read-only: nothing in this graph writes to the service.
"""

from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from admin_client import AdminClient
from prompts import build_messages
from schemas import Recommendation, validate_recommendation
from signals import compute_signals

MAX_ATTEMPTS = 3  # first try + 2 corrections


class AdvisorState(TypedDict, total=False):
    minutes: int
    only_clients: Optional[list[str]]
    client_ids: list[str]
    reports: dict[str, dict]
    signals: dict[str, dict]
    index: int
    attempts: int
    feedback: list[str]
    draft: Optional[Recommendation]
    draft_error: Optional[str]
    recommendations: list[dict]
    rejected: list[dict]
    skipped: list[dict]


def build_graph(admin: AdminClient, llm: Any):
    """
    `llm` is anything with .invoke(messages) -> Recommendation, normally a chat
    model wrapped with .with_structured_output(Recommendation). Injecting it
    keeps the graph testable without a real API key.
    """

    def observe(state: AdvisorState) -> AdvisorState:
        minutes = state["minutes"]
        ids = state.get("only_clients") or admin.list_clients()
        reports, signals, active, skipped = {}, {}, [], []
        for cid in ids:
            report = admin.usage(cid, minutes)
            if report["totals"]["total"] == 0:
                skipped.append({"client_id": cid, "reason": f"no traffic in the last {minutes} minutes"})
                continue
            reports[cid] = report
            signals[cid] = compute_signals(report)
            active.append(cid)
        return {
            "client_ids": active, "reports": reports, "signals": signals, "skipped": skipped,
            "index": 0, "attempts": 0, "feedback": [], "recommendations": [], "rejected": [],
        }

    def analyze(state: AdvisorState) -> AdvisorState:
        cid = state["client_ids"][state["index"]]
        messages = build_messages(cid, state["reports"][cid], state["signals"][cid], state["feedback"])
        try:
            draft = llm.invoke(messages)
            if not isinstance(draft, Recommendation):
                raise ValueError(f"expected a Recommendation, got {type(draft).__name__}")
            return {"draft": draft, "draft_error": None, "attempts": state["attempts"] + 1}
        except Exception as e:  # malformed output, API error, rate limit...
            return {"draft": None, "draft_error": f"{type(e).__name__}: {e}", "attempts": state["attempts"] + 1}

    def validate(state: AdvisorState) -> AdvisorState:
        cid = state["client_ids"][state["index"]]
        current = state["reports"][cid]["policy"]["policy"]
        draft = state["draft"]

        errors = ([f"the response could not be used ({state['draft_error']})"] if draft is None
                  else validate_recommendation(draft, cid, current))

        if not errors:
            entry = {**draft.model_dump(), "current_policy": current,
                     "signals": state["signals"][cid], "attempts": state["attempts"]}
            return {"recommendations": state["recommendations"] + [entry],
                    "index": state["index"] + 1, "attempts": 0, "feedback": []}

        if state["attempts"] >= MAX_ATTEMPTS:
            # Give up on this client rather than show an unvalidated recommendation.
            entry = {"client_id": cid, "errors": errors, "attempts": state["attempts"]}
            return {"rejected": state["rejected"] + [entry],
                    "index": state["index"] + 1, "attempts": 0, "feedback": []}

        return {"feedback": errors}  # same client, try again with the errors

    def after_observe(state: AdvisorState) -> str:
        return "analyze" if state["client_ids"] else END

    def after_validate(state: AdvisorState) -> str:
        return "analyze" if state["index"] < len(state["client_ids"]) else END

    graph = StateGraph(AdvisorState)
    graph.add_node("observe", observe)
    graph.add_node("analyze", analyze)
    graph.add_node("validate", validate)
    graph.add_edge(START, "observe")
    graph.add_conditional_edges("observe", after_observe, ["analyze", END])
    graph.add_edge("analyze", "validate")
    graph.add_conditional_edges("validate", after_validate, ["analyze", END])
    return graph.compile()


def run_once(admin: AdminClient, llm: Any, minutes: int, only_clients: Optional[list[str]] = None) -> dict:
    app = build_graph(admin, llm)
    # Each analyze/validate pair is 2 steps; leave room for retries on every client.
    return app.invoke({"minutes": minutes, "only_clients": only_clients},
                      config={"recursion_limit": 1000})
