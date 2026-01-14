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

Agent 负责监听日志文件，检测到错误后，将 “repo_url + error_content” 推给服务端。

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
  repo_url = "https://tencentgit.dabby.com.cn/iam/iammanager.git"
  error_content = "ValueError: boom"
  code_host = "gitlab"
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
  -d "{\"repo_url\":\"https://tencentgit.dabby.com.cn/iam/iammanager.git\",\"error_content\":\"ValueError: boom\",\"code_host\":\"gitlab\"}"
```
