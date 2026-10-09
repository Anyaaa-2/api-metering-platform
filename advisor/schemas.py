"""
The structured output the LLM must produce, and the guardrails that
check it. A recommendation that fails validation is sent back to the
model with the errors (see graph.py) instead of being shown to anyone.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Action = Literal["NO_CHANGE", "UPGRADE_TIER", "REDUCE_FREE_QUOTA", "THROTTLE_SUSPECTED_ABUSE"]

MAX_CHANGE_FACTOR = 10        # no limit may move more than 10x in one recommendation
MAX_WINDOW_SECONDS = 86_400   # mirrors Policy.java


class ProposedPolicy(BaseModel):
    freeLimit: int
    maxRequests: int
    unitCostPaise: int
    windowSeconds: int


class Recommendation(BaseModel):
    client_id: str = Field(description="The client this recommendation is about.")
    action: Action = Field(description="The single recommended action.")
    proposed_policy: Optional[ProposedPolicy] = Field(
        default=None,
        description="The full new policy. Must be null when action is NO_CHANGE.",
    )
    confidence: Literal["low", "medium", "high"]
    reasoning: str = Field(description="Two or three sentences explaining the recommendation.")
    evidence: list[str] = Field(
        description="Specific numbers from the signals that support the recommendation."
    )


def validate_policy_rules(p: ProposedPolicy) -> list[str]:
    """Same rules the Java service enforces on PUT /admin/policy."""
    errors = []
    if p.freeLimit < 0:
        errors.append("freeLimit must be >= 0")
    if p.maxRequests < 1:
        errors.append("maxRequests must be >= 1")
    if p.freeLimit > p.maxRequests:
        errors.append("freeLimit must not exceed maxRequests")
    if p.unitCostPaise < 0:
        errors.append("unitCostPaise must be >= 0")
    if not 1 <= p.windowSeconds <= MAX_WINDOW_SECONDS:
        errors.append(f"windowSeconds must be between 1 and {MAX_WINDOW_SECONDS}")
    return errors


def validate_recommendation(rec: Recommendation, client_id: str, current: dict) -> list[str]:
    """Returns a list of problems; an empty list means the recommendation is acceptable."""
    errors = []

    if rec.client_id != client_id:
        errors.append(f"client_id must be '{client_id}', got '{rec.client_id}'")
    if not rec.evidence:
        errors.append("evidence must contain at least one specific number from the signals")

    p = rec.proposed_policy
    if rec.action == "NO_CHANGE":
        if p is not None:
            errors.append("proposed_policy must be null when action is NO_CHANGE")
        return errors
    if p is None:
        return errors + [f"proposed_policy is required for action {rec.action}"]

    errors += validate_policy_rules(p)

    # Pricing and window length are business decisions, not the advisor's.
    if p.unitCostPaise != current["unitCostPaise"]:
        errors.append("unitCostPaise must stay unchanged; the advisor does not change prices")
    if p.windowSeconds != current["windowSeconds"]:
        errors.append("windowSeconds must stay unchanged")

    if p.freeLimit == current["freeLimit"] and p.maxRequests == current["maxRequests"]:
        errors.append(f"action {rec.action} must actually change the policy")

    # Each action must move the limits in the direction its name implies.
    if rec.action == "UPGRADE_TIER" and p.maxRequests <= current["maxRequests"]:
        errors.append("UPGRADE_TIER must increase maxRequests")
    if rec.action == "THROTTLE_SUSPECTED_ABUSE" and p.maxRequests >= current["maxRequests"]:
        errors.append("THROTTLE_SUSPECTED_ABUSE must decrease maxRequests")
    if rec.action == "REDUCE_FREE_QUOTA":
        if p.freeLimit >= current["freeLimit"]:
            errors.append("REDUCE_FREE_QUOTA must decrease freeLimit")
        if p.maxRequests != current["maxRequests"]:
            errors.append("REDUCE_FREE_QUOTA must leave maxRequests unchanged")

    # Blast-radius guardrail: no single recommendation moves a limit too far.
    for field in ("freeLimit", "maxRequests"):
        old, new = current[field], getattr(p, field)
        if old > 0 and new > 0 and max(old, new) / min(old, new) > MAX_CHANGE_FACTOR:
            errors.append(f"{field} may change by at most {MAX_CHANGE_FACTOR}x (from {old} to {new})")

    return errors
