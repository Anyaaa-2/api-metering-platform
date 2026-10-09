"""
Run the AI usage advisor against the metering service.

    python run_advisor.py --url http://127.0.0.1:PORT --admin-key dev-admin-key
    python run_advisor.py ... --interval 300      # keep running every 5 minutes

The model is chosen with ADVISOR_MODEL as "<provider>:<model>", e.g.
    google_genai:gemini-3.1-flash-lite   (needs GOOGLE_API_KEY)
    anthropic:claude-sonnet-5-5          (needs ANTHROPIC_API_KEY)
    openai:<model-name>                  (needs OPENAI_API_KEY)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from admin_client import AdminClient
from graph import run_once
from schemas import Recommendation

DEFAULT_MODEL = "google_genai:gemini-3.1-flash-lite"


def make_llm():
    from langchain.chat_models import init_chat_model

    model_id = os.environ.get("ADVISOR_MODEL", DEFAULT_MODEL)
    model = init_chat_model(model_id, temperature=0)
    # Newer Claude models return structured output through native JSON schema
    # rather than forced tool calling; the other providers use their default.
    if model_id.startswith("anthropic:"):
        return model.with_structured_output(Recommendation, method="json_schema")
    return model.with_structured_output(Recommendation)


def fmt_policy(p: dict) -> str:
    return f"free {p['freeLimit']}, max {p['maxRequests']}, {p['unitCostPaise']}p/req, {p['windowSeconds']}s window"


def print_report(result: dict) -> None:
    print(f"\n=== Usage advisor report  {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    for rec in result.get("recommendations", []):
        s = rec["signals"]
        print(f"\n[{rec['action']}] {rec['client_id']}  (confidence: {rec['confidence']})")
        print(f"  traffic : {s['total_requests']} requests over {s['active_minutes']} active min, "
              f"{s['blocked_requests']} blocked, revenue {s['revenue_paise']}p")
        print(f"  current : {fmt_policy(rec['current_policy'])}")
        if rec["proposed_policy"]:
            print(f"  proposed: {fmt_policy(rec['proposed_policy'])}")
        print(f"  why     : {rec['reasoning']}")
        for e in rec["evidence"]:
            print(f"            - {e}")
        if rec["attempts"] > 1:
            print(f"  note    : accepted after {rec['attempts']} attempts (validator corrections)")
    for r in result.get("rejected", []):
        print(f"\n[REJECTED] {r['client_id']}: no valid recommendation after {r['attempts']} attempts")
        for e in r["errors"]:
            print(f"            - {e}")
    for s in result.get("skipped", []):
        print(f"\n[SKIPPED] {s['client_id']}: {s['reason']}")
    if not any(result.get(k) for k in ("recommendations", "rejected", "skipped")):
        print("\nNo clients found. Run the traffic simulator first.")
    print("\nRecommend-only: no policy was changed.")


def save(result: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"recommendations-{datetime.now():%Y%m%d-%H%M%S}.json")
    with open(path, "w") as f:
        json.dump({k: result.get(k, []) for k in ("recommendations", "rejected", "skipped")}, f, indent=2)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="AI usage advisor (recommend-only)")
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--admin-key", default=os.environ.get("ADMIN_API_KEY", "dev-admin-key"))
    ap.add_argument("--minutes", type=int, default=15, help="how much history to analyze")
    ap.add_argument("--client", action="append", help="only analyze this client (repeatable)")
    ap.add_argument("--interval", type=int, default=0, help="seconds between runs; 0 = run once")
    ap.add_argument("--out", default="reports", help="directory for JSON reports")
    args = ap.parse_args()

    admin = AdminClient(args.url, args.admin_key)
    llm = make_llm()

    while True:
        try:
            result = run_once(admin, llm, args.minutes, args.client)
            print_report(result)
            print(f"Saved: {save(result, args.out)}")
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            if not args.interval:
                return 1
        if not args.interval:
            return 0
        print(f"\nNext run in {args.interval}s (Ctrl+C to stop)")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
