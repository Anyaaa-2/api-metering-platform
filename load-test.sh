#!/bin/bash
# Usage: ./load-test.sh [base-url]     (default: http://localhost:8080)
#
# Fires 15 requests as one client and shows which zone each one lands in.
# With the default policy you should see:
#   1-5   -> 200 FREE
#   6-10  -> 200 BILLABLE  (bill grows by 50 paise each)
#   11-15 -> 429 BLOCKED
#
# Pointed at the Kubernetes Service, requests round-robin across pods, so
# a clean result proves the quota AND the bill are shared, not per-pod.

URL="${1:-http://localhost:8080}"
CLIENT="load-test-$(date +%s)"   # fresh client each run, so old windows don't interfere

for i in $(seq 1 15); do
  headers=$(curl -s -o /dev/null -D - -H "X-Client-Id: $CLIENT" "$URL/api/resource")
  code=$(echo "$headers" | head -1 | awk '{print $2}')
  state=$(echo "$headers" | grep -i '^x-usage-state:' | awk '{print $2}' | tr -d '\r')
  bill=$(echo "$headers" | grep -i '^x-bill-paise:' | awk '{print $2}' | tr -d '\r')
  printf "Request %2d -> HTTP %s  %-8s  bill: %s paise\n" "$i" "$code" "$state" "$bill"
done
