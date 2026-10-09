# Distributed API Metering Platform

A Spring Boot service that meters, bills, and throttles API usage per client,
built to stay exact across many replicas. Each client has a policy:

| Requests in a window          | Zone       | Result                                |
|-------------------------------|------------|---------------------------------------|
| 1 .. `freeLimit`              | `FREE`     | served, not charged                   |
| `freeLimit+1` .. `maxRequests`| `BILLABLE` | served, charged `unitCostPaise` each  |
| beyond `maxRequests`          | `BLOCKED`  | `429 Too Many Requests`, not charged  |

Cost per window = `max(0, min(used, maxRequests) - freeLimit) x unitCostPaise`,
accumulated into a running bill.

## Architecture

```
            HOT PATH (every request, deterministic, ~1 Redis round trip)
client --> MeteringInterceptor --> metering.lua in Redis --> FREE / BILLABLE / BLOCKED
                                      reads   policy:<id>
                                      writes  usage:<id>, bill:<id>, history:<id>:<minute>

            CONTROL PLANE (operators, and the AI usage advisor)
/admin/** (API key) --> read usage history, read/update policies
```

### Design decisions

- **One atomic Lua script does everything.** Counting, classifying, billing and
  recording history happen as a single Redis operation, so two pods can never
  interleave between "count this request" and "charge for it". This keeps
  both the quota and the bill exact under concurrent load.
- **Money is stored as integer paise**, never floats, so the bill can't drift.
- **Blocked requests are never charged.**
- **Policies live in Redis**, so a change applies on the client's very next
  request, on every pod, with no redeploy.
- **The AI advisor stays out of the request path.** An LLM call per request
  would add seconds of latency, cost money per request, and make enforcement
  non-deterministic. The advisor reads usage through the admin API and only
  recommends policy changes.
- **The admin API fails closed.** Without `ADMIN_API_KEY` configured it is
  disabled, because the service runs behind a public LoadBalancer.

## Run locally

```bash
docker compose up --build
```

The app runs at `http://localhost:8080`. Locally the admin key is `dev-admin-key`.

## Try it

```bash
./load-test.sh          # 15 requests: 5 FREE, 5 BILLABLE, 5 BLOCKED
./test-metering.sh      # pass/fail checks, including a concurrency test
```

Every `/api/**` response carries the metering result in headers:
`X-Usage-State`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
`X-Free-Remaining`, `X-Bill-Paise` (plus `Retry-After` when blocked).

## Admin API

All endpoints require the header `X-Admin-Key`.

| Method   | Path                                 | Purpose                                    |
|----------|--------------------------------------|--------------------------------------------|
| `GET`    | `/admin/clients`                     | all clients seen so far                    |
| `GET`    | `/admin/policy/{clientId}`           | effective policy (custom or default)       |
| `PUT`    | `/admin/policy/{clientId}`           | set a custom policy (validated)            |
| `DELETE` | `/admin/policy/{clientId}`           | revert to the default policy               |
| `GET`    | `/admin/usage/{clientId}?minutes=60` | bill, current window, per-minute history   |

```bash
curl -X PUT http://localhost:8080/admin/policy/acme \
  -H "X-Admin-Key: dev-admin-key" -H "Content-Type: application/json" \
  -d '{"freeLimit":100,"maxRequests":1000,"unitCostPaise":20,"windowSeconds":60}'

curl -H "X-Admin-Key: dev-admin-key" "http://localhost:8080/admin/usage/acme?minutes=30"
```

## Configuration

In `src/main/resources/application.properties`:

- `metering.default-free-limit` (5), `metering.default-max-requests` (10),
  `metering.default-unit-cost-paise` (50), `metering.default-window-seconds` (60):
  the policy for clients without a custom one
- `metering.history-ttl-seconds` (86400): how long per-minute history is kept
- `metering.admin-api-key`: set via the `ADMIN_API_KEY` environment variable

## Deploy to Kubernetes

Create the admin key Secret once, then apply the manifests:

```bash
kubectl create secret generic metering-admin --from-literal=admin-key=<choose-a-strong-key>
kubectl apply -f k8s/
kubectl get pods -w      # 1 redis pod + app pods
```

Then run both scripts against the Service URL. Requests round-robin across
pods, so passing results prove the quota and the bill are shared across
replicas rather than tracked per pod:

```bash
./load-test.sh http://<service-ip>:8080
./test-metering.sh http://<service-ip>:8080 <your-admin-key>
```

## AI usage advisor (`advisor/`)

A LangGraph agent that reads usage through the admin API and recommends
policy changes. It is **recommend-only**: it never writes to the service.

```
observe ──► analyze ──► validate ──┬──► analyze  (rejected: retry with the validator's errors)
              ▲                    ├──► analyze  (accepted: next client)
              └────────────────────┘
                                   └──► END      (all clients done)
```

- **observe** fetches each client's usage and computes signals in plain Python
  (blocked ratio, peak-to-median ratio, free-quota utilization, revenue lost to
  blocks). The LLM gets finished numbers because models are unreliable at arithmetic.
- **analyze** asks the LLM for one structured recommendation per client:
  `NO_CHANGE`, `UPGRADE_TIER`, `REDUCE_FREE_QUOTA` or `THROTTLE_SUSPECTED_ABUSE`,
  with a proposed policy, confidence, reasoning and cited evidence.
- **validate** checks the recommendation against guardrails: the same policy
  rules as the Java service, the action must move limits in the right direction,
  prices and window length can't change, and no limit can move more than 10x.
  On failure, the errors go back to the model for a corrected answer, up to
  3 attempts. A client that never gets a valid answer is reported as rejected,
  never shown as a recommendation.

### Run it

```bash
cd advisor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GOOGLE_API_KEY=<your-key>        # free key from Google AI Studio
# optional: export ADVISOR_MODEL=anthropic:claude-sonnet-5-5   (with ANTHROPIC_API_KEY)

python simulator.py --url http://127.0.0.1:<port> --minutes 6    # ~6 minutes, real time
python run_advisor.py --url http://127.0.0.1:<port> --minutes 15
```

The simulator runs four clients with distinct patterns (one that keeps hitting
its limit, one healthy paid user, one light user, one with a sudden burst), so
the expected answers are known in advance. Each run's report is saved as JSON in
`advisor/reports/`. Add `--interval 300` to keep the advisor running every 5 minutes.

### Tests (no API key or server needed)

```bash
cd advisor && python -m pytest -q
```

The graph test uses a scripted fake LLM and a fake admin API to cover the
whole loop: a correction after validator feedback, a client rejected after
3 failed attempts, a skipped idle client, and a check that the advisor only
ever sends GET requests.

## Roadmap

- Human approval step: an operator reviews a recommendation and applies it
  through `PUT /admin/policy`, keeping a person in the loop for every change
