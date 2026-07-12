<p align="center">
  <button id="btn-en" onclick="switchLang('en')" style="background:#238636;color:#fff;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;margin:2px">English</button>
  <button id="btn-zh" onclick="switchLang('zh')" style="background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:4px 12px;border-radius:4px;cursor:pointer;margin:2px">中文</button>
</p>

<div id="lang-en">

<p align="center">
  <img src="https://raw.githubusercontent.com/jjjkkll157/agentgate/master/docs/dashboard-screenshot.png" alt="AgentGate Dashboard" width="720">
</p>

---

AgentGate is a local HTTP proxy for AI agent tool calls. It sits between your agent and the external APIs it calls, handling retries, rate limits, circuit breaking, and error formatting. One `pip install`, one YAML file, no cloud, no Kubernetes. Runs on `localhost:9400`.

If you have built an AI agent that calls external tools (search APIs, email, databases, anything with an HTTP endpoint), you know the drill: 429s at peak traffic, random 500s from upstream, schema changes that break your JSON parsing, connection drops mid-request. Every codebase copies the same retry boilerplate, and every codebase gets it slightly wrong.

AgentGate does this once, right, as a local sidecar.

## Install

```bash
pip install agentgate
```

Python 3.10 or newer.

## Quick start

Create `tools.yaml`:

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

Start it:

```bash
agentgate --config tools.yaml
```

Call a tool:

```bash
curl -X GET "http://localhost:9400/tool/web_search?q=test"
```

Dashboard at `http://localhost:9400/dashboard`.

## What you get

- **Automatic retry** with exponential backoff and jitter. Configurable per tool.
- **Rate limit awareness**. Reads `X-RateLimit-Remaining` headers from responses and throttles locally before hitting hard limits.
- **Circuit breaker**. N consecutive failures and the breaker trips. Requests fast-fail for a cooldown, then a single probe checks if the upstream is back.
- **Structured errors**. Every failure returns `{"error": true, "reason": "circuit_open", "retry_after": 30}`. Your agent parses these instead of choking on raw HTML error pages.
- **Result caching**. Same params return cached data within the TTL window. Saves API costs.
- **Fallback chains**. Primary tool fails, try the next one in your list.
- **Web dashboard** at `localhost:9400/dashboard`. Shows every request, latency, error rate. Switches between English and Chinese.

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
      ttl_seconds: 300         # 0 disables caching
    fallback:
      - backup_search
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

## Why not use [agentgateway](https://github.com/agentgateway/agentgateway)?

Agentgateway is an enterprise agent governance layer built for Kubernetes. It requires CRDs, Gateway API, and a cluster to run. AgentGate is a single process you start with `pip install && agentgate start`. Same root concept, different user. Agentgateway is for platform teams managing hundreds of agents across an organization. AgentGate is for a developer who wants their tool calls to stop breaking.

## License

MIT

</div>

<div id="lang-zh" style="display:none">

<p align="center">
  <img src="https://raw.githubusercontent.com/jjjkkll157/agentgate/master/docs/dashboard-screenshot.png" alt="AgentGate Dashboard" width="720">
</p>

---

AgentGate 是一个本地 HTTP 代理，专门解决 AI Agent 调用外部工具时的可靠性问题。它架在 Agent 和外部 API 之间，自动处理重试、限流、熔断和错误格式化。`pip install` 安装，一个 YAML 文件配置，不依赖云服务，不需要 Kubernetes，就在 `localhost:9400` 上跑。

写过一个 AI Agent 你就知道：搜素 API 突然返回 429，上游随机 500，JSON 格式偷偷变了导致解析炸掉，连接半路断开。每个项目都在复制粘贴同样的重试代码，写得五花八门，修了一遍又一遍。

AgentGate 把这件事做一次、做对。

## 安装

```bash
pip install agentgate
```

需要 Python 3.10 以上。

## 快速开始

创建 `tools.yaml`：

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

- **自动重试** — 指数退避加随机抖动，每个工具独立配置。
- **限流感知** — 读取 API 返回的 `X-RateLimit-Remaining` 头，快到上限时自动降速排队。
- **熔断保护** — 连续 N 次失败后跳闸，冷却时间内直接拒绝请求，随后用一次探测判断上游是否恢复。
- **结构化错误** — 所有失败返回 `{"error": true, "reason": "circuit_open", "retry_after": 30}`，Agent 能解析处理，而不是面对一坨原始 HTML 报错页面。
- **结果缓存** — 同样参数在 TTL 窗口内直接返回缓存，省 API 费用。
- **降级链路** — 主工具挂了自动切备用工具。
- **Web 面板** — `localhost:9400/dashboard` 实时看请求量、延迟、错误率。支持中英文切换。

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
      ttl_seconds: 300         # 0 关闭缓存
    fallback:
      - backup_search
```

## 运行流程

```
  AI Agent
     │
     │  POST /tool/web_search {"q": "..."}
     ▼
┌─────────────────────┐
│   AgentGate :9400   │
│                     │
│  缓存 → 命中？直接返回
│  限流 → 令牌不足则排队
│  熔断 → 断路中直接拒绝
│  重试 → 429/5xx → 等待 → 重试
│  降级 → 重试耗尽后切备用
│  转发 → 真实 API
└─────────────────────┘
```

## 和 [agentgateway](https://github.com/agentgateway/agentgateway) 有什么区别？

Agentgateway 是企业级 Agent 治理网关，需要 Kubernetes 集群、CRD 和 Gateway API 才能跑。AgentGate 是单个进程，`pip install && agentgate start` 就行。核心思路类似，但面向完全不同的用户——Agentgateway 是给平台团队管理上百个 Agent 用的，AgentGate 是给一个开发者写的，让他的工具调用别老挂。

## 许可证

MIT

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
