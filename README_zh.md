<p align="center">
  <img src="https://raw.githubusercontent.com/jjjkkll157/agentgate/master/docs/dashboard-screenshot.png" alt="AgentGate 仪表盘" width="720">
</p>

<p align="center">
  <a href="https://github.com/jjjkkll157/agentgate/actions/workflows/test.yml"><img src="https://github.com/jjjkkll157/agentgate/actions/workflows/test.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/version-0.2.0-brightgreen" alt="v0.2.0">
  <img src="https://img.shields.io/badge/tests-64%20passing-ok" alt="64 个测试">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
</p>

<p align="center">
  <a href="README.md">English</a> &nbsp;|&nbsp;
  <a href="README_zh.md"><b>简体中文</b></a>
</p>

> ⚠️ **未经作者明确书面许可，禁止将本代码用于任何商业用途。**
> 如需商业授权，请联系：**liluelue7@gmail.com** / **2586329235@qq.com**

---

<p align="center"><code>pip install git+https://github.com/jjjkkll157/agentgate.git</code></p>

AgentGate 是一个本地 HTTP 代理，专门解决 AI Agent 调用外部工具时的可靠性问题。架在 Agent 和外部 API 之间，自动处理重试、限流、熔断和错误格式化。`pip install` 安装，一个 YAML 文件配置，不依赖云服务，不需要 Kubernetes，在 `localhost:9400` 上跑。

写过 AI Agent 的都知道：搜索 API 突然 429，上游随机 500，JSON 格式偷偷变了导致解析炸掉，连接半路断开。每个项目都在复制粘贴同样的重试代码，写得五花八门，修了一遍又一遍。

AgentGate 把这件事做一次、做对。

## 安装

```bash
pip install git+https://github.com/jjjkkll157/agentgate.git
```

Python 3.10 以上。

## 快速开始

创建 `tools.yaml`，或用 [`presets/`](presets/) 里的预设：

```bash
# 方式 A：直接套用预设
cp presets/brave-search.yaml tools.yaml

# 方式 B：自己写
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

| 功能 | 说明 |
|------|------|
| 自动重试 | 指数退避 + 随机抖动。遵守上游 `Retry-After` 头 |
| 限流感知 | 读取 API 返回的 `X-RateLimit-Remaining`，同步本地令牌桶 |
| 熔断保护 | 连续 N 次失败后跳闸，冷却后只放一个探测请求 |
| 并发控制 | 每个工具可配 `max_concurrent`，`asyncio.BoundedSemaphore` |
| Schema 校验 | 请求前后做 JSON Schema 输入/输出校验 |
| 中间件钩子 | 自定义 `before`/`after` Python 函数，每个工具独立配置 |
| 结构化错误 | 统一返回 `{"error":true,"reason":"..."}`，Agent 能解析 |
| 结果缓存 | TTL 内同样参数直接返回缓存。上限 1 万条，LRU 淘汰 |
| 降级链路 | 主工具挂了自动切备用 |
| 健康探测 | 后台定时检查各工具健康端点，结果同步到熔断器 |
| Web 面板 | `localhost:9400/dashboard`，中英切换，支持搜索过滤 |
| 请求重放 | `POST /dashboard/api/replay/{index}` — 一键重跑历史请求 |
| 熔断器管理 | `GET /api/breakers` + `POST /api/breakers/{name}/reset` |
| Prometheus 指标 | `localhost:9400/metrics` — 计数器、每工具延迟直方图 |
| 优雅关闭 | SIGTERM 时排空所有正在处理的请求。`/health` 显示 `draining` |
| 鉴权 | Bearer Token 白名单，不配置即关闭 |
| API 预设 | Brave Search、Resend、GitHub — 即插即用，[`presets/`](presets/) |

## 预设

开箱即用的工具配置，在 [`presets/`](presets/) 里：

| 预设 | 文件 | 需要的环境变量 |
|------|------|---------------|
| Brave Search | `brave-search.yaml` | `BRAVE_API_KEY` |
| Resend 邮件 | `resend.yaml` | `RESEND_API_KEY` |
| GitHub API | `github.yaml` | `GITHUB_TOKEN`、`GITHUB_REPO` |

```bash
cp presets/brave-search.yaml tools.yaml
# 改好环境变量，然后：
agentgate --config tools.yaml
```

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
    concurrency:
      max_concurrent: 10       # 0 = 不限制
    timeout: 30.0
    cache:
      ttl_seconds: 300         # 0 关闭缓存
    fallback:
      - backup_search
    middleware:
      before: []
      after: []
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

## API 速查

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 断路器状态、工具列表、是否排空中 |
| `/version` | GET | 版本号 |
| `/metrics` | GET | Prometheus 格式指标 |
| `/tool/{name}` | GET/POST/… | 代理调用注册的工具 |
| `/dashboard/` | GET | Web 控制台 |
| `/dashboard/api/log` | GET | 可搜索请求日志 `?tool=X&error_only=1&q=…` |
| `/dashboard/api/replay/{idx}` | POST | 重放历史请求 |
| `/dashboard/api/breakers` | GET | 所有断路器状态 |
| `/dashboard/api/breakers/{n}/reset` | POST | 强制重置断路器 |

## 和 agentgateway 有什么区别？

[agentgateway](https://github.com/agentgateway/agentgateway) 是企业级 Agent 治理网关，需要 Kubernetes 集群、CRD 和 Gateway API 才能跑。AgentGate 是单个进程，`pip install && agentgate start` 就行。核心思路类似，但面向完全不同的用户——agentgateway 是给平台团队管理上百个 Agent 用的，AgentGate 是给一个开发者写的，让他的工具调用别老挂。

## 许可证

MIT —— 附带商用限制（见上方警示）。
