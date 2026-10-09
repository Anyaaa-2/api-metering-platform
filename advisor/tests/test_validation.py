import pytest

from schemas import ProposedPolicy, Recommendation, validate_recommendation
from signals import compute_signals

CURRENT = {"freeLimit": 5, "maxRequests": 10, "unitCostPaise": 50, "windowSeconds": 60}


def rec(action, policy=None, client="acme", evidence=("blocked 36 of 96 requests",)):
    return Recommendation(
        client_id=client, action=action,
        proposed_policy=ProposedPolicy(**policy) if policy else None,
        confidence="high", reasoning="test", evidence=list(evidence),
    )


def with_(**changes):
    return {**CURRENT, **changes}


def test_valid_upgrade_passes():
    assert validate_recommendation(rec("UPGRADE_TIER", with_(maxRequests=20)), "acme", CURRENT) == []


def test_valid_no_change_passes():
    assert validate_recommendation(rec("NO_CHANGE"), "acme", CURRENT) == []


def test_no_change_with_policy_rejected():
    errors = validate_recommendation(rec("NO_CHANGE", with_(maxRequests=20)), "acme", CURRENT)
    assert any("must be null" in e for e in errors)


def test_missing_policy_rejected():
    errors = validate_recommendation(rec("UPGRADE_TIER"), "acme", CURRENT)
    assert any("required" in e for e in errors)


def test_wrong_client_rejected():
    errors = validate_recommendation(rec("NO_CHANGE", client="other"), "acme", CURRENT)
    assert any("client_id" in e for e in errors)


def test_empty_evidence_rejected():
    errors = validate_recommendation(rec("NO_CHANGE", evidence=()), "acme", CURRENT)
    assert any("evidence" in e for e in errors)


@pytest.mark.parametrize("action,policy,fragment", [
    ("UPGRADE_TIER", with_(maxRequests=8), "increase maxRequests"),
    ("THROTTLE_SUSPECTED_ABUSE", with_(maxRequests=12), "decrease maxRequests"),
    ("REDUCE_FREE_QUOTA", with_(freeLimit=6), "decrease freeLimit"),
    ("REDUCE_FREE_QUOTA", with_(freeLimit=2, maxRequests=12), "leave maxRequests unchanged"),
])
def test_action_direction_enforced(action, policy, fragment):
    assert any(fragment in e for e in validate_recommendation(rec(action, policy), "acme", CURRENT))


def test_price_change_rejected():
    errors = validate_recommendation(rec("UPGRADE_TIER", with_(maxRequests=20, unitCostPaise=10)), "acme", CURRENT)
    assert any("does not change prices" in e for e in errors)


def test_window_change_rejected():
    errors = validate_recommendation(rec("UPGRADE_TIER", with_(maxRequests=20, windowSeconds=120)), "acme", CURRENT)
    assert any("windowSeconds must stay unchanged" in e for e in errors)


def test_blast_radius_guardrail():
    errors = validate_recommendation(rec("UPGRADE_TIER", with_(maxRequests=500)), "acme", CURRENT)
    assert any("at most 10x" in e for e in errors)


def test_java_policy_rules_mirrored():
    errors = validate_recommendation(rec("THROTTLE_SUSPECTED_ABUSE", with_(freeLimit=5, maxRequests=3)), "acme", CURRENT)
    assert any("must not exceed maxRequests" in e for e in errors)


def test_signals_math():
    report = {
        "minutesCovered": 15,
        "policy": {"policy": CURRENT, "customPolicy": False},
        "totals": {"total": 30, "free": 10, "billable": 10, "blocked": 10, "costPaise": 500},
        "history": [
            {"minute": "m1", "total": 2, "free": 2, "billable": 0, "blocked": 0, "costPaise": 0},
            {"minute": "m2", "total": 2, "free": 2, "billable": 0, "blocked": 0, "costPaise": 0},
            {"minute": "m3", "total": 26, "free": 6, "billable": 10, "blocked": 10, "costPaise": 500},
        ],
    }
    s = compute_signals(report)
    assert s["active_minutes"] == 3
    assert s["blocked_ratio"] == 0.333
    assert s["blocked_revenue_paise"] == 500
    assert s["minutes_with_blocks"] == 1
    assert s["peak_to_median_ratio"] == 13.0
    assert s["avg_requests_per_active_minute"] == 10.0
