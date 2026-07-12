# AgentGate

A local HTTP proxy that sits between your AI agent and its tools.  
It retries failures, backs off on rate limits, opens a circuit when a
tool is unhealthy, and returns structured errors the agent can parse.
Instead of raw 500 HTML pages.

No cloud. No K8s. Just `pip install` and point your tools at
`localhost:9400`.

## Why

AI agents call external APIs — search, email, extraction, databases.
Those APIs fail. A lot. Rate limits, schema changes, 5xx errors,
connection drops.

The standard fix is wrapping every tool call in the same retry/backoff
boilerplate. Every project copies it. Every project gets it slightly
wrong. AgentGate does it once, correctly, as a local sidecar you
configure in YAML.

## Install

```bash
pip install agentgate
```

Requires Python 3.10+.

## Quick start

1. Write a `tools.yaml`:

```yaml
tools:
  web_search:
    endpoint: https://api.search.brave.com/res/v1/web/search
    method: GET
    headers:
      X-Subscription-Token: "${BRAVE_API_KEY}"
    retry:
      max_attempts: 3
    ratelimit:
      max_per_minute: 20
    circuit_breaker:
      failure_threshold: 5
      cooldown_seconds: 30
```

2. Start the proxy:

```bash
agentgate --config tools.yaml
```

3. Call a tool through the proxy:

```bash
curl -X GET "http://localhost:9400/tool/web_search?q=test"
```

4. Open the dashboard at http://localhost:9400/dashboard

## What you get

- **Retry** — exponential backoff with jitter. Configurable per tool.
- **Rate limit aware** — reads `X-RateLimit-Remaining` headers, throttles
  locally so you don't hit hard limits.
- **Circuit breaker** — after N consecutive failures, stops forwarding
  requests for a cooldown period. Lets the downstream recover.
- **Structured errors** — every failure returns `{"error": true, "reason":
  "circuit_open", "retry_after": 30}`. The agent can act on these instead
  of choking on raw HTML.
- **Caching** — same-parameter calls return cached results within a TTL
  you set. Saves API costs.
- **Fallback chains** — primary tool fails? AgentGate tries the next one
  in your list automatically.
- **Dashboard** — `localhost:9400/dashboard` shows every request, latency,
  errors. No external service needed.

## Tool config reference

```yaml
tools:
  my_tool:
    endpoint: https://api.example.com/v1/action
    method: POST               # default: POST
    headers:                   # static headers, ${ENV_VAR} for secrets
      Authorization: "Bearer ${MY_API_KEY}"
    retry:
      max_attempts: 3          # default: 3
      backoff: exponential     # exponential | linear | fixed
      initial_delay: 1.0       # seconds
      max_delay: 60.0          # seconds cap
    ratelimit:
      max_per_minute: 60       # local token bucket
    circuit_breaker:
      failure_threshold: 5     # consecutive failures to trip
      cooldown_seconds: 30     # time before testing again
    timeout: 30.0              # per-request timeout (seconds)
    cache:
      ttl_seconds: 300         # 0 = no cache
    fallback:                  # ordered list of other tool names
      - backup_search
    schema:
      input: {}                # JSON Schema (coming soon)
      output: {}
```

## Architecture

```
  AI Agent
     │
     │  POST /tool/web_search {"q": "..."}
     ▼
┌─────────────────────┐
│   AgentGate :9400   │
│   (this project)    │
│                     │
│  ┌───────────────┐  │
│  │ cache    ─────│──│──→ cached? return immediately
│  └───────┬───────┘  │
│          ▼           │
│  ┌───────────────┐  │
│  │ rate limit ───│──│──→ queue if no tokens
│  └───────┬───────┘  │
│          ▼           │
│  ┌───────────────┐  │
│  │ circuit brk ──│──│──→ reject if open
│  └───────┬───────┘  │
│          ▼           │
│  ┌───────────────┐  │
│  │ retry loop   ──│──│──→ 429/5xx → wait → retry
│  └───────┬───────┘  │
│          ▼           │
│  ┌───────────────┐  │
│  │ fallback     ──│──│──→ try backup tool if all retries fail
│  └───────┬───────┘  │
│          ▼           │
│  ┌───────────────┐  │
│  │ forward req   │  │──→ real API
│  └───────────────┘  │
└─────────────────────┘
```

## Related projects

- [agentgateway](https://github.com/agentgateway/agentgateway) (Linux
  Foundation) — enterprise agent governance for K8s. Heavy, production
  control-plane. Not a local dev tool.
- [LiteLLM](https://github.com/BerriAI/litellm) — LLM API proxy with
  retry for OpenAI-format endpoints. LLM-only; doesn't do general tool
  APIs.
- [Portkey](https://portkey.ai) — commercial AI gateway. SaaS.

If your agent calls external APIs and you're tired of writing the same
retry logic in every project, AgentGate handles it in one config file.

## License

MIT
