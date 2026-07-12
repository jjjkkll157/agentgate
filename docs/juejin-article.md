# AgentGate：一行命令给你的 AI Agent 加上企业级弹性层

> 本地运行。不传数据到云端。一个 YAML 文件搞定。

---

你写过 AI Agent 吗？调用外部 API 的时候，下面这些你肯定遇到过：

- 搜索 API 突然回 429，你的 Agent 直接崩了
- 上游随机 500，重试三次还是 500，Agent 卡死
- JSON 返回格式偷偷变了，解析炸掉
- 连接半路断开，整个对话废了

然后你在 `try/except` 里套 `try/except`，手写指数退避，给每个 API 单独写重试逻辑。写着写着发现这段代码和上个项目里的几乎一模一样——复制过来，修修改改，总感觉哪里不对。

我写 AgentGate 就是解决这个。一个本地 HTTP 代理，架在你的 Agent 和外部 API 之间。配好 YAML，启动，它自己处理重试、限流、熔断、缓存。

---

## 怎么装

```bash
pip install git+https://github.com/jjjkkll157/agentgate.git
```

Python 3.10+。没有别的依赖。

---

## 一分钟跑起来

创建 `tools.yaml`，定义你要调用的外部 API：

```yaml
tools:
  web_search:
    endpoint: https://api.search.brave.com/res/v1/web/search
    method: GET
    headers:
      X-Subscription-Token: "${BRAVE_API_KEY}"
    retry:
      max_attempts: 3
      backoff: exponential
    ratelimit:
      max_per_minute: 20
    circuit_breaker:
      failure_threshold: 5
      cooldown_seconds: 30
    timeout: 15.0
    cache:
      ttl_seconds: 300
```

`${BRAVE_API_KEY}` 会自动从环境变量读取。

启动：

```bash
agentgate --config tools.yaml
```

```
AgentGate v0.1.0 — listening on http://127.0.0.1:9400
dashboard: http://127.0.0.1:9400/dashboard
metrics:  http://127.0.0.1:9400/metrics
```

![AgentGate Dashboard](https://raw.githubusercontent.com/jjjkkll157/agentgate/master/docs/dashboard-screenshot.png)

然后你的 Agent 把原来直接调 API 的代码改成走 AgentGate：

```bash
# 原来：直接调 Brave Search
curl "https://api.search.brave.com/res/v1/web/search?q=test"

# 现在：走 AgentGate
curl "http://localhost:9400/tool/web_search?q=test"
```

AgentGate 收到请求后，自动走完一整套弹性管线，然后把结果（或结构化错误）返回。

---

## 它具体做了什么

请求进来后，经过下面这些层：

```
  AI Agent
     │  POST /tool/web_search {"q": "AI"}
     ▼
┌─────────────────────────────────┐
│         AgentGate :9400         │
│                                 │
│  schema 校验 → 参数类型不对？直接拒绝
│  缓存查询   → 刚才查过？直接返回，省一次 API 调用
│  熔断检查   → 连续挂了 5 次？跳闸，快速失败
│  限流排队   → 令牌桶，每分钟最多 20 次
│  并发控制   → 同时最多 N 个请求，超了排队
│  重试循环   → 429/5xx → 等几秒 → 重试
│  降级链路   → 主 API 彻底挂了？切备用的
│  转发       → 调用真实 API
│  schema 校验 → 返回格式不对？重试或报错
│  缓存写入   → 成功结果存起来，下次直接复用
└─────────────────────────────────┘
```

每一步都是可配置的。你不需要写一行重试代码。

**真实指标面板**（localhost:9400/metrics）：

```
# 总共 6 次请求，0 次走缓存，6 次有错误（httpbin 太慢超时了）
agentgate_requests_total 6
agentgate_cache_hits_total 0
agentgate_errors_total 6
agentgate_latency_seconds_echo_get_bucket{le="0.01"} 0
agentgate_latency_seconds_echo_get_bucket{le="5.0"} 0
agentgate_latency_seconds_echo_get_bucket{le="10.0"} 2
agentgate_latency_seconds_echo_get_bucket{le="30.0"} 4
agentgate_latency_seconds_echo_get_bucket{le="+Inf"} 4
```

被监控的对象是你定义的工具。每个 API 有独立的延迟分布、错误率、缓存命中率。

**结构化错误返回**（Agent 能直接解析）：

```json
{
  "error": true,
  "reason": "circuit_open",
  "detail": "circuit open for 'web_search'",
  "retry_after": 25.3,
  "circuit_open": true,
  "request_id": "a1b2c3d4e5f6"
}
```

Agent 拿到这个之后知道自己该等 25 秒再试，而不是对着原始 HTML 报错页面发呆。

---

## 可配置的全部能力

| 能力 | 干什么的 | 怎么配 |
|------|---------|--------|
| 自动重试 | 指数退避 + 抖动，遵守 `Retry-After` 头 | `retry.max_attempts: 3` |
| 限流感知 | 读取 `X-RateLimit-Remaining`，同步本地令牌桶 | `ratelimit.max_per_minute: 60` |
| 熔断保护 | 连续失败 N 次 → 跳闸 → 冷却 → 探测 | `circuit_breaker.failure_threshold: 5` |
| Schema 校验 | 请求前后做 JSON Schema 类型检查 | `schema.input.required: [q]` |
| 中间件钩子 | 自定义 Python 函数做前置/后置处理 | `middleware.before: [myapp.hooks.log]` |
| 结果缓存 | TTL 内同参数直接返回 | `cache.ttl_seconds: 300` |
| 并发控制 | 信号量限流，防打爆上游 | `concurrency.max_concurrent: 10` |
| 降级链路 | 主挂了自动切备用工具 | `fallback: [backup_search]` |
| 健康探测 | 后台定时检查工具端点 | `health.endpoint: /health` |

完整配置参考：

```yaml
tools:
  my_tool:
    endpoint: https://api.example.com/v1/action
    method: POST
    headers:
      Authorization: "Bearer ${MY_API_KEY}"
    retry:
      max_attempts: 3
      backoff: exponential
      initial_delay: 1.0
      max_delay: 60.0
    ratelimit:
      max_per_minute: 60
    circuit_breaker:
      failure_threshold: 5
      cooldown_seconds: 30
    concurrency:
      max_concurrent: 10
    timeout: 30.0
    cache:
      ttl_seconds: 300
    fallback:
      - backup_tool
    middleware:
      before:
        - myproject.hooks.validate_auth
      after:
        - myproject.hooks.strip_sensitive
    health:
      endpoint: https://api.example.com/health
    schema:
      input:
        required: [query]
        properties:
          query: {type: string}
      output:
        required: [results]
```

---

## 和同类项目的区别

[agentgateway](https://github.com/agentgateway/agentgateway) 是企业级 Agent 治理网关，需要 Kubernetes 集群、CRD 和 Gateway API。面向平台团队管理上百个 Agent。

AgentGate 是单个 Python 进程。`pip install` 然后 `agentgate start`。面向一个开发者，让他的工具调用别老挂。

不是竞品——是两个不同量级的东西。如果你跑 K8s 当然用 agentgateway。如果你只是想让自己的小项目 Agent 别三天两头被 429 卡死，AgentGate 够了。

---

## 测试覆盖

47 个测试覆盖了重试策略、令牌桶、熔断器三态机、schema 校验（含 `isinstance(True, int)` 坑）、并发控制、缓存驱逐、Retry-After HTTP-date 解析、中间件链等。CI 自动跑 Python 3.10/3.11/3.12。

---

## 许可

MIT 开源。但 **未经作者书面许可，禁止商用**。有商业需求联系 liluelue7@gmail.com。

---

仓库：[github.com/jjjkkll157/agentgate](https://github.com/jjjkkll157/agentgate)

有问题提 Issue，PR 欢迎。
