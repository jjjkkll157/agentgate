# AgentGate

<p align="center">
  <button id="btn-en" onclick="switchLang('en')" style="background:#238636;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;margin:2px">English</button>
  <button id="btn-zh" onclick="switchLang('zh')" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:4px 12px;border-radius:4px;cursor:pointer;margin:2px">中文</button>
</p>

<div id="lang-en">

A local HTTP proxy for AI agent tool calls. Handles retries, rate limits,
circuit breaking, and structured error formatting. One `pip install`, one
YAML config file. No cloud, no K8s — runs on `localhost:9400`.

</div>

<div id="lang-zh" style="display:none">

一个本地 HTTP 代理，专门处理 AI Agent 的工具调用可靠性。
自动重试、感知速率限制、熔断保护、结构化错误返回。
`pip install` 安装，一个 YAML 配置文件启动。不依赖云服务，不需要
Kubernetes，就在 `localhost:9400` 上跑。

</div>

<script>
function switchLang(lang) {
  document.getElementById('lang-en').style.display = lang === 'en' ? 'block' : 'none';
  document.getElementById('lang-zh').style.display = lang === 'zh' ? 'block' : 'none';
  document.getElementById('btn-en').style.background = lang === 'en' ? '#238636' : '#21262d';
  document.getElementById('btn-en').style.color = lang === 'en' ? '#fff' : '#c9d1d9';
  document.getElementById('btn-en').style.border = lang === 'en' ? 'none' : '1px solid #30363d';
  document.getElementById('btn-zh').style.background = lang === 'zh' ? '#238636' : '#21262d';
  document.getElementById('btn-zh').style.color = lang === 'zh' ? '#fff' : '#c9d1d9';
  document.getElementById('btn-zh').style.border = lang === 'zh' ? 'none' : '1px solid #30363d';
}
</script>

---

<div id="lang-en">

## Why

AI agents call external APIs — search, email, extraction, databases.
Those APIs fail often. Rate limits, schema changes, 5xx errors,
connection drops.

Every project copies the same retry boilerplate. Every project gets
it slightly wrong. AgentGate does it once, correctly, as a local
sidecar you configure in YAML.

## Install

```bash
pip install agentgate
```

Python 3.10+.

## Quick start

Write a `tools.yaml`:

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

Start:

```bash
agentgate --config tools.yaml
```

Call a tool:

```bash
curl -X GET "http://localhost:9400/tool/web_search?q=test"
```

Dashboard at `http://localhost:9400/dashboard`.

## What you get

- **Retry** — exponential backoff with jitter. Per-tool config.
- **Rate limit aware** — reads `X-RateLimit-Remaining` headers,
  throttles locally.
- **Circuit breaker** — N consecutive failures → stops forwarding
  for a cooldown, then tests with one probe.
- **Structured errors** — every failure returns
  `{"error": true, "reason": "circuit_open", "retry_after": 30}`.
  Agents parse these instead of choking on raw HTML.
- **Caching** — same params → cached response within TTL.
- **Fallback chains** — primary tool fails, try the next one in your list.
- **Dashboard** — `localhost:9400/dashboard` shows every request,
  latency, errors.

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
    timeout: 30.0
    cache:
      ttl_seconds: 300         # 0 = no cache
    fallback:
      - backup_search
```

## Architecture

```
  AI Agent
     │
     │  POST /tool/web_search {"q": "..."}
     ▼
┌─────────────────────┐
│   AgentGate :9400   │
│                     │
│  cache ──→ hit? return cached
│  rate limit ──→ queue if no tokens
│  circuit brk ──→ reject if open
│  retry loop ──→ 429/5xx → wait → retry
│  fallback ──→ try backups on exhaustion
│  forward ──→ real API
└─────────────────────┘
```

## Related

- [agentgateway](https://github.com/agentgateway/agentgateway) —
  enterprise agent governance for K8s. Not a local dev tool.
- [LiteLLM](https://github.com/BerriAI/litellm) — LLM API proxy.
  LLM-only; doesn't handle general tool APIs.

## License

MIT

</div>

<div id="lang-zh" style="display:none">

## 为什么

AI Agent 调用外部 API——搜索、邮件、数据提取——这些 API 经常挂。
限流、schema 变更、5xx 错误、连接断开。

每个项目都在复制粘贴同样的重试代码，写得到处都不一样。
AgentGate 把这件事做一次、做对——一个本地 sidecar，一个 YAML 文件搞定。

## 安装

```bash
pip install agentgate
```

需要 Python 3.10+。

## 快速开始

写一个 `tools.yaml`：

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

启动：

```bash
agentgate --config tools.yaml
```

调用工具：

```bash
curl -X GET "http://localhost:9400/tool/web_search?q=test"
```

监控面板：`http://localhost:9400/dashboard`

## 功能

- **自动重试** — 指数退避 + 随机抖动。每个工具独立配置。
- **速率限制感知** — 读取 `X-RateLimit-Remaining` 响应头，本地排队。
- **熔断器** — 连续 N 次失败后停止转发，冷却后探测恢复。
- **结构化错误** — 所有失败返回统一格式，Agent 能解析处理。
- **缓存** — 相同参数的调用在 TTL 内直接返回缓存，省 API 费用。
- **降级链路** — 主工具挂了自动切备用工具。
- **监控面板** — `localhost:9400/dashboard` 实时查看请求、延迟、错误。

## 配置参考

```yaml
tools:
  my_tool:
    endpoint: https://api.example.com/v1/action
    method: POST               # 默认 POST
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
    timeout: 30.0
    cache:
      ttl_seconds: 300         # 0 = 不缓存
    fallback:
      - backup_search
```

## 架构

```
  AI Agent
     │
     │  POST /tool/web_search {"q": "..."}
     ▼
┌─────────────────────┐
│   AgentGate :9400   │
│                     │
│  缓存 ──→ 命中？直接返回
│  限流 ──→ 没令牌就排队
│  熔断 ──→ 熔断中直接拒绝
│  重试 ──→ 429/5xx → 等待 → 重试
│  降级 ──→ 重试耗尽后切备用
│  转发 ──→ 真实 API
└─────────────────────┘
```

## 相关项目

- [agentgateway](https://github.com/agentgateway/agentgateway) —
  企业级 Agent 治理网关，需要 K8s。不是本地开发工具。
- [LiteLLM](https://github.com/BerriAI/litellm) — LLM API 代理。
  只管 LLM 调用，不管通用工具 API。

## 许可证

MIT

</div>
