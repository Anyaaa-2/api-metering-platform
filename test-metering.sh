#!/bin/bash
# Usage: ./test-metering.sh [base-url] [admin-key]
#   defaults: http://localhost:8080  dev-admin-key
#
# End-to-end checks with pass/fail assertions:
#   1. the admin API rejects requests without the key
#   2. invalid policies are rejected
#   3. requests move through FREE -> BILLABLE -> BLOCKED in order
#   4. the bill is exactly right
#   5. under concurrent load (across all pods when run against Kubernetes),
#      the quota and the bill are still exact - no lost or double charges

URL="${1:-http://localhost:8080}"
KEY="${2:-dev-admin-key}"
RUN=$(date +%s)
PASS=0
FAIL=0

check() {
  if [ "$2" == "$3" ]; then
    echo "PASS  $1"; PASS=$((PASS + 1))
  else
    echo "FAIL  $1 (expected '$2', got '$3')"; FAIL=$((FAIL + 1))
  fi
}
admin_status() {
  curl -s -o /dev/null -w "%{http_code}" -H "X-Admin-Key: $KEY" -H "Content-Type: application/json" "$@"
}
bill_of() {
  curl -s -H "X-Admin-Key: $KEY" "$URL/admin/usage/$1" | grep -o '"billPaise":[0-9]*' | cut -d: -f2
}

echo "== Admin API security =="
check "rejects missing admin key" 401 \
  "$(curl -s -o /dev/null -w '%{http_code}' "$URL/admin/clients")"

echo "== Policy validation =="
check "rejects freeLimit > maxRequests" 400 \
  "$(admin_status -X PUT -d '{"freeLimit":10,"maxRequests":5,"unitCostPaise":10,"windowSeconds":60}' "$URL/admin/policy/bad-$RUN")"

echo "== Zones and billing (free 3, max 6, 100 paise) =="
C="zones-$RUN"
check "accepts valid policy" 200 \
  "$(admin_status -X PUT -d '{"freeLimit":3,"maxRequests":6,"unitCostPaise":100,"windowSeconds":120}' "$URL/admin/policy/$C")"
STATES=""
for i in $(seq 1 9); do
  s=$(curl -s -o /dev/null -D - -H "X-Client-Id: $C" "$URL/api/resource" \
      | grep -i '^x-usage-state:' | awk '{print $2}' | tr -d '\r')
  STATES="$STATES$s "
done
check "zones in order" "FREE FREE FREE BILLABLE BILLABLE BILLABLE BLOCKED BLOCKED BLOCKED " "$STATES"
check "bill = 3 billable x 100 paise" 300 "$(bill_of "$C")"

echo "== Concurrency: 200 requests, 25 in parallel (free 20, max 120, 7 paise) =="
C="concurrent-$RUN"
admin_status -X PUT -d '{"freeLimit":20,"maxRequests":120,"unitCostPaise":7,"windowSeconds":300}' \
  "$URL/admin/policy/$C" > /dev/null
CODES=$(seq 1 200 | xargs -P 25 -I{} \
  curl -s -o /dev/null -w "%{http_code}\n" -H "X-Client-Id: $C" "$URL/api/resource")
check "exactly 120 served" 120 "$(echo "$CODES" | grep -c '^200$')"
check "exactly 80 blocked" 80 "$(echo "$CODES" | grep -c '^429$')"
check "bill exact: 100 billable x 7 paise" 700 "$(bill_of "$C")"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
