"""
End-to-end test of the agent loop with a fake admin API (httpx.MockTransport)
and a scripted fake LLM, so it runs without a server or an API key.
"""

import httpx

from admin_client import AdminClient
from graph import MAX_ATTEMPTS, run_once
from schemas import ProposedPolicy, Recommendation

POLICY = {"freeLimit": 5, "maxRequests": 10, "unitCostPaise": 50, "windowSeconds": 60}


def report(client, per_minute):
    history = []
    for i, n in enumerate(per_minute):
        free, billable = min(n, 5), max(0, min(n, 10) - 5)
        history.append({"minute": f"m{i}", "total": n, "free": free, "billable": billable,
                        "blocked": max(0, n - 10), "costPaise": billable * 50})
    totals = {k: sum(b[k] for b in history) for k in ("total", "free", "billable", "blocked", "costPaise")}
    return {"clientId": client, "policy": {"clientId": client, "policy": POLICY, "customPolicy": False},
            "currentWindowUsed": 0, "windowResetsInSeconds": 0, "billPaise": totals["costPaise"],
            "minutesCovered": 15, "totals": totals, "history": history}


REPORTS = {
    "acme-corp": report("acme-corp", [16] * 6),
    "steady-co": report("steady-co", [8] * 6),
    "flaky": report("flaky", [8] * 6),
    "idle": report("idle", []),
}


def fake_admin():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Admin-Key"] == "k"
        assert request.method == "GET", "the advisor must never write"
        if request.url.path == "/admin/clients":
            return httpx.Response(200, json=list(REPORTS))
        client = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=REPORTS[client])
    return AdminClient("http://test", "k", transport=httpx.MockTransport(handler))


def rec(client, action, **policy):
    return Recommendation(
        client_id=client, action=action,
        proposed_policy=ProposedPolicy(**{**POLICY, **policy}) if policy else None,
        confidence="high", reasoning="r", evidence=["e"],
    )


class ScriptedLLM:
    """Returns pre-written answers per client, in order, and records the prompts it saw."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.prompts = []

    def invoke(self, messages):
        human = messages[-1][1]
        self.prompts.append(human)
        client = next(c for c in self.script if f'"client_id": "{c}"' in human)
        answer = self.script[client].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_full_loop_with_retry_rejection_and_skip():
    llm = ScriptedLLM({
        # wrong direction first, then corrected after validator feedback
        "acme-corp": [rec("acme-corp", "UPGRADE_TIER", maxRequests=8),
                      rec("acme-corp", "UPGRADE_TIER", maxRequests=20)],
        "steady-co": [rec("steady-co", "NO_CHANGE")],
        # never produces anything valid -> rejected, not shown as a recommendation
        "flaky": [ValueError("bad json"), rec("flaky", "UPGRADE_TIER", unitCostPaise=1, maxRequests=20),
                  rec("flaky", "NO_CHANGE", maxRequests=20)],
    })

    result = run_once(fake_admin(), llm, minutes=15)

    accepted = {r["client_id"]: r for r in result["recommendations"]}
    assert set(accepted) == {"acme-corp", "steady-co"}
    assert accepted["acme-corp"]["proposed_policy"]["maxRequests"] == 20
    assert accepted["acme-corp"]["attempts"] == 2
    assert accepted["steady-co"]["action"] == "NO_CHANGE"

    assert [r["client_id"] for r in result["rejected"]] == ["flaky"]
    assert result["rejected"][0]["attempts"] == MAX_ATTEMPTS

    assert [s["client_id"] for s in result["skipped"]] == ["idle"]

    # The retry prompt must carry the validator's error back to the model.
    retry_prompt = llm.prompts[1]
    assert "rejected by the validator" in retry_prompt
    assert "UPGRADE_TIER must increase maxRequests" in retry_prompt


def test_no_clients_ends_cleanly():
    def handler(request):
        return httpx.Response(200, json=[])
    admin = AdminClient("http://test", "k", transport=httpx.MockTransport(handler))
    result = run_once(admin, ScriptedLLM({}), minutes=15)
    assert result["client_ids"] == []
    assert result.get("recommendations", []) == []
