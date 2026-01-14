# Agent + Server（先自研 Agent，后接日志平台）

## 1) 服务端启动

1. 配置环境变量（示例）

```bash
CODE_HOST=gitlab
GITLAB_BASE_URL=https://tencentgit.dabby.com.cn
GITLAB_TOKEN=xxx
GITLAB_PROJECT=iam/iammanager

SMTP_USER=xxx
SMTP_PASSWORD=xxx
RECEIVER_EMAIL=xxx

CLAUDE_COMMAND=claude

HTTP_HOST=127.0.0.1
HTTP_PORT=8080

SERVER_API_KEY=optional_shared_key
```

2. 启动 HTTP 服务

```bash
python scripts/server.py
```

## 2) Agent 启动（每个项目一个）

Agent 负责监听日志文件（或对接 ELK 等日志平台），检测到错误后，将“结构化错误事件（Event Contract v1）”推给服务端。

### 2.1 为什么不传 log-path 给 Server

`--log-path` 是 Agent 所在机器的本地文件路径。通常 Server 部署在另一台机器/容器中：
- Server 无法访问该本地文件（路径不通）
- 即便路径可达也不安全（权限过大、容易泄漏敏感信息）

因此 `log-path` 只用于 Agent 本地读取日志，Server 只接收“可传输的错误事件内容”。

### 2.2 事件 Payload（建议标准）

当前实现最小字段是：
- `repo_url`：目标仓库 clone 地址
- `error_content`：错误事件内容（可包含 traceback）
- `code_host`：gitlab/github

为了更好地做去重与相似检索（bug 库/知识库），建议逐步扩展为结构化事件（字段可选）：
- `event_id`：uuid
- `timestamp`：事件时间（unix 秒）
- `service`：服务名/模块名
- `environment`：prod/staging/dev
- `error_raw`：原始错误片段（截断后）
- `error_norm`：归一化后的错误文本（去路径/时间戳/随机数等噪声）
- `exception_type`：如 ValueError/NullPointerException
- `message_key`：归一化后的 message 关键短语（适合检索）
- `frames`：堆栈关键帧（文件名/函数名/行号，建议只取项目内前 N 帧）
- `fingerprint`：对 (exception_type + message_key + frames) 的 hash
- `context_before` / `context_after`：错误前后日志窗口（可选，需脱敏/截断）

归一化建议（`error_norm` / `message_key`）：
- 替换时间戳、uuid、绝对路径、内存地址（0x...）、大数字为占位符
- 保留异常类型、关键 message、项目内关键栈帧（file:function）

示例：

```bash
set AGENT_API_KEY=optional_shared_key
python scripts/agent.py ^
  --log-path "C:\path\to\app.log" ^
  --repo-url "https://tencentgit.dabby.com.cn/iam/iammanager.git" ^
  --server-url "http://127.0.0.1:8080" ^
  --code-host gitlab
```

## 3) curl / PowerShell 测试

PowerShell 推荐：

```powershell
$payload = @{
  schema_version = "1.0"
  event_id = "00000000-0000-0000-0000-000000000000"
  occurred_at = 1730000000
  repo = @{
    repo_url = "https://tencentgit.dabby.com.cn/iam/iammanager.git"
    code_host = "gitlab"
    default_branch = "main"
  }
  service = @{
    name = "iammanager"
    environment = "staging"
  }
  error = @{
    exception_type = "ValueError"
    message_key = "invalid literal for int base 10"
    fingerprint = "sha256..."
    frames = @(
      @{ file = "app.py"; function = "handle" }
    )
    raw_excerpt = "ValueError: boom"
  }
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8080/v1/tasks" `
  -ContentType "application/json" `
  -Headers @{ "X-API-Key" = "optional_shared_key" } `
  -Body $payload
```

真实 curl（Windows 用 curl.exe）：

```bash
curl.exe -sS -X POST "http://127.0.0.1:8080/v1/tasks" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: optional_shared_key" ^
  -d "{\"schema_version\":\"1.0\",\"event_id\":\"00000000-0000-0000-0000-000000000000\",\"occurred_at\":1730000000,\"repo\":{\"repo_url\":\"https://tencentgit.dabby.com.cn/iam/iammanager.git\",\"code_host\":\"gitlab\",\"default_branch\":\"main\"},\"service\":{\"name\":\"iammanager\",\"environment\":\"staging\"},\"error\":{\"exception_type\":\"ValueError\",\"message_key\":\"invalid literal for int base 10\",\"fingerprint\":\"sha256...\",\"frames\":[{\"file\":\"app.py\",\"function\":\"handle\"}],\"raw_excerpt\":\"ValueError: boom\"}}"
 ```
