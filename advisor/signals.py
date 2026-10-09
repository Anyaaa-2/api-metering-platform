"""
Turns a raw usage report into a small set of numeric signals.

The arithmetic happens here, in plain Python, on purpose: LLMs are
unreliable at math, so the model is handed finished numbers and only
has to reason about what they mean.
"""

from statistics import median


def compute_signals(report: dict) -> dict:
    policy = report["policy"]["policy"]
    history = report["history"]
    totals = report["totals"]

    per_minute = [b["total"] for b in history]
    active_minutes = len(per_minute)
    avg = sum(per_minute) / active_minutes if active_minutes else 0.0
    peak = max(per_minute, default=0)
    typical = median(per_minute) if per_minute else 0

    # Requests per policy window, so usage can be compared to the limits
    # even when windowSeconds is not 60.
    per_window_avg = avg * policy["windowSeconds"] / 60

    return {
        "minutes_observed": report["minutesCovered"],
        "active_minutes": active_minutes,
        "total_requests": totals["total"],
        "free_requests": totals["free"],
        "billable_requests": totals["billable"],
        "blocked_requests": totals["blocked"],
        "revenue_paise": totals["costPaise"],
        # revenue missed because requests were blocked instead of billed
        "blocked_revenue_paise": totals["blocked"] * policy["unitCostPaise"],
        "blocked_ratio": round(totals["blocked"] / totals["total"], 3) if totals["total"] else 0.0,
        "minutes_with_blocks": sum(1 for b in history if b["blocked"] > 0),
        "avg_requests_per_active_minute": round(avg, 1),
        "peak_requests_in_a_minute": peak,
        "median_requests_per_active_minute": typical,
        "peak_to_median_ratio": round(peak / typical, 1) if typical else 0.0,
        "avg_requests_per_window": round(per_window_avg, 1),
        "free_quota_utilization": round(min(per_window_avg / policy["freeLimit"], 9.99), 2)
        if policy["freeLimit"] else 0.0,
    }
