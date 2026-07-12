<p align="center">
  <img src="https://raw.githubusercontent.com/jjjkkll157/agentgate/master/docs/dashboard-screenshot.png" alt="AgentGate Dashboard" width="720">
</p>

<p align="center">
  <a href="https://github.com/jjjkkll157/agentgate/actions/workflows/test.yml"><img src="https://github.com/jjjkkll157/agentgate/actions/workflows/test.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/version-0.2.0-brightgreen" alt="v0.2.0">
  <img src="https://img.shields.io/badge/tests-64%20passing-ok" alt="64 tests">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> &nbsp;|&nbsp;
  <a href="README_zh.md">简体中文</a>
</p>

> ⚠️ **Commercial use of this code is prohibited without explicit written permission from the author.**
> For commercial licensing inquiries: **liluelue7@gmail.com** / **2586329235@qq.com**

---

<p align="center"><code>pip install git+https://github.com/jjjkkll157/agentgate.git</code></p>

AgentGate is a local HTTP proxy for AI agent tool calls. It sits between your agent and the external APIs it calls, handling retries, rate limits, circuit breaking, and error formatting. One `pip install`, one YAML file, no cloud, no Kubernetes. Runs on `localhost:9400`.

If you have built an AI agent that calls external tools — search APIs, email, databases, anything with an HTTP endpoint — you know the drill: 429s at peak traffic, random 500s from upstream, schema changes that break your JSON parsing, connection drops mid-request. Every codebase copies the same retry boilerplate, and every codebase gets it slightly wrong.

AgentGate does this once, right, as a local sidecar.

## Install

```bash
pip install git+https://github.com/jjjkkll157/agentgate.git
```

Python 3.10 or newer.

## Quick start

Create `tools.yaml` — or pick a preset from [`presets/`](presets/):

```bash
# Option A: start from a preset
cp presets/brave-search.yaml tools.yaml

# Option B: write your own
cat > tools.yaml << 'EOF'
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
    cache:
      ttl_seconds: 300
EOF
```

Start it:

```bash
agentgate --config tools.yaml
```

Call a tool:

```bash
curl -X GET "http://localhost:9400/tool/web_search?q=test"
```

Dashboard at `http://localhost:9400/dashboard`.

## Capabilities

| Capability | Detail |
|------------|--------|
| Auto retry | Exponential backoff + jitter. Honors `Retry-After` headers. |
| Rate limit aware | Reads `X-RateLimit-Remaining` from API responses, syncs token bucket. |
| Circuit breaker | N failures → trip → cooldown → one probe → recover or re-trip. |
| Concurrency cap | Per-tool `max_concurrent` — `asyncio.BoundedSemaphore`. |
| Schema validation | Input/output JSON Schema checks before and after every call. |
| Middleware hooks | User-defined `before` / `after` Python hooks per tool. |
| Structured errors | `{"error":true,"reason":"circuit_open","retry_after":30}` — agents parse these. |
| Result cache | Same params → cached response within TTL. 10K-entry ceiling, LRU eviction. |
| Fallback chains | Primary fails → try the next tool in your list. |
| Health probes | Background periodic health checks, synced to circuit breaker. |
| Web dashboard | `localhost:9400/dashboard` — real-time log, EN/中 toggle, search & filter. |
| Dashboard replay | `POST /dashboard/api/replay/{index}` — re-run any logged request. |
| Breaker control | `GET /api/breakers` + `POST /api/breakers/{name}/reset` from dashboard. |
| Prometheus metrics | `localhost:9400/metrics` — counters, latency histograms per tool. |
| Graceful shutdown | Drains in-flight requests on SIGTERM. `/health` reports `draining`. |
| Auth | Bearer-token allowlist. Zero-config when disabled. |
| API presets | Drop-in configs for Brave Search, Resend, GitHub — [`presets/`](presets/). |

## Presets

Ready-to-use tool configs in [`presets/`](presets/):

| Preset | File | Env var needed |
|--------|------|---------------|
| Brave Search | `brave-search.yaml` | `BRAVE_API_KEY` |
| Resend Email | `resend.yaml` | `RESEND_API_KEY` |
| GitHub API | `github.yaml` | `GITHUB_TOKEN`, `GITHUB_REPO` |

```bash
cp presets/brave-search.yaml tools.yaml
# edit the env vars, then:
agentgate --config tools.yaml
```

## Config reference

```yaml
tools:
  my_tool:
    endpoint: https://api.example.com/v1/action
    method: POST               # default: POST
    headers:
      Authorization: "Bearer ${MY_API_KEY}"
    retry:
      max_attempts: 3
      backoff: exponential     # exponential | linear | fixed
      initial_delay: 1.0
      max_delay: 60.0
    ratelimit:
      max_per_minute: 60
    circuit_breaker:
      failure_threshold: 5
      cooldown_seconds: 30
    concurrency:
      max_concurrent: 10       # 0 = unlimited
    timeout: 30.0
    cache:
      ttl_seconds: 300         # 0 disables caching
    fallback:
      - backup_search
    middleware:
      before: []
      after: []
```

## How it works

```
  AI Agent
     │
     │  POST /tool/web_search {"q": "..."}
     ▼
┌─────────────────────┐
│   AgentGate :9400   │
│                     │
│  cache  → hit? return cached
│  rate limit → queue if no tokens left
│  circuit breaker → reject if circuit open
│  retry loop → 429/5xx → wait → retry
│  fallback → try backup tools on exhaustion
│  forward → real API
└─────────────────────┘
```

## API quick reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Breaker states, tool list, drain status |
| `/version` | GET | Version string |
| `/metrics` | GET | Prometheus format |
| `/tool/{name}` | GET/POST/… | Proxy call to registered tool |
| `/dashboard/` | GET | Web UI |
| `/dashboard/api/log` | GET | Searchable request log `?tool=X&error_only=1&q=…` |
| `/dashboard/api/replay/{idx}` | POST | Replay logged request |
| `/dashboard/api/breakers` | GET | All breaker states |
| `/dashboard/api/breakers/{n}/reset` | POST | Force-reset a breaker |

## Why not use agentgateway?

[agentgateway](https://github.com/agentgateway/agentgateway) is an enterprise agent governance layer built for Kubernetes. It requires CRDs, Gateway API, and a cluster to run. AgentGate is a single process — `pip install && agentgate start`. Same root concept, different user. Agentgateway is for platform teams managing hundreds of agents. AgentGate is for a developer who needs their tool calls to stop breaking.

## License

MIT — with commercial-use restriction (see notice above).
