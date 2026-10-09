"""
Traffic simulator: four clients with deliberately different behaviour,
so the advisor has real patterns to find. With the default policy
(free 5, max 10 per 60s window):

  acme-corp     16 req/min, every minute     -> keeps hitting the block      (expect UPGRADE_TIER)
  steady-co      8 req/min                   -> healthy paid usage           (expect NO_CHANGE)
  tiny-startup   1 req/min                   -> stays inside the free quota  (expect NO_CHANGE)
  spiky-bot      2 req/min, then a burst of 80 in one minute                 (expect THROTTLE_SUSPECTED_ABUSE)

    python simulator.py --url http://127.0.0.1:PORT --minutes 6

History is bucketed per real minute, so this runs in real time.
"""

import argparse
import threading
import time

import httpx

CLIENTS = ["acme-corp", "steady-co", "tiny-startup", "spiky-bot"]


def requests_for(client: str, minute: int, total_minutes: int) -> int:
    if client == "acme-corp":
        return 16
    if client == "steady-co":
        return 8
    if client == "tiny-startup":
        return 1
    if client == "spiky-bot":
        return 80 if minute == total_minutes - 2 else 2  # burst in the second-to-last minute
    raise ValueError(client)


def run_client(client: str, url: str, minutes: int, start: float, results: dict, lock: threading.Lock):
    with httpx.Client(base_url=url, timeout=10.0) as http:
        for minute in range(minutes):
            n = requests_for(client, minute, minutes)
            minute_start = start + minute * 60
            for i in range(n):
                # Spread the minute's requests evenly instead of firing them all at once.
                time.sleep(max(0.0, minute_start + i * (55 / n) - time.time()))
                try:
                    status = http.get("/api/resource", headers={"X-Client-Id": client}).status_code
                except httpx.HTTPError:
                    status = "error"
                with lock:
                    results[client][status] = results[client].get(status, 0) + 1
            with lock:
                served = results[client].get(200, 0)
                blocked = results[client].get(429, 0)
            print(f"  minute {minute + 1}/{minutes}  {client:<13} sent {n:>3}  "
                  f"(running total: {served} served, {blocked} blocked)")


def reset_policies(url: str, admin_key: str) -> None:
    """Start every simulated client from the default policy, so runs are repeatable."""
    with httpx.Client(base_url=url, headers={"X-Admin-Key": admin_key}, timeout=10.0) as http:
        for client in CLIENTS:
            r = http.delete(f"/admin/policy/{client}")
            if r.status_code != 200:
                raise SystemExit(f"Could not reset policy for {client}: HTTP {r.status_code}. Check --admin-key.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate realistic traffic patterns")
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--admin-key", default="dev-admin-key")
    ap.add_argument("--minutes", type=int, default=6)
    args = ap.parse_args()

    reset_policies(args.url, args.admin_key)
    print(f"Simulating {len(CLIENTS)} clients for {args.minutes} minutes...")

    results = {c: {} for c in CLIENTS}
    lock = threading.Lock()
    start = time.time()
    threads = [threading.Thread(target=run_client, args=(c, args.url, args.minutes, start, results, lock))
               for c in CLIENTS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\nDone. Totals:")
    for c in CLIENTS:
        print(f"  {c:<13} served {results[c].get(200, 0):>4}   blocked {results[c].get(429, 0):>4}")
    print("\nNow run the advisor:  python run_advisor.py --url ... --minutes 15")


if __name__ == "__main__":
    main()
