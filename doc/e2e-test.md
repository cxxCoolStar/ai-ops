# 端到端测试步骤（Agent → Server → Claude → PR → 邮件）

本文档用于在本机复现一整套闭环流程：应用输出日志 →（可选）ELK 收集 → Agent 拉取错误并上报 Server → Server 拉取仓库、调用 Claude 生成修复、提交分支并创建 PR → 发送邮件通知。

## 0. 前置条件

- Python 环境可用（能运行 `python`）
- 依赖已安装（例如 `watchdog`、`python-dotenv`、`PyGithub` 等）
- 本机能访问 GitHub 与邮箱 SMTP
- Claude CLI 可用（`CLAUDE_COMMAND` 指向可执行命令）
- 如使用 ELK 模式：本机可访问 Elasticsearch（`ELK_URL`）

## 1. 准备被修复的示例仓库

本流程以示例仓库为目标：

- GitHub：`https://github.com/cxxCoolStar/ai-ops-example`
- 本机路径：`C:\Users\asta1\PycharmProjects\ai-ops-example`
- 日志文件：`C:\Users\asta1\PycharmProjects\ai-ops-example\app.log`

确保仓库能正常运行（`python app.py` 会在日志中写入 ERROR + Traceback）。

## 2. 配置环境变量

在 `ai-ops` 工程目录下配置 `.env`（推荐）或直接设置系统环境变量。

### 2.1 GitHub（用于 push 分支 + 创建 PR）

- `CODE_HOST=github`
- `GITHUB_TOKEN=<GitHub PAT，需具备 push/PR 权限>`

说明：
- Server 会根据 `repo_url` 自动识别 `owner/repo`，所以不强制要求 `GITHUB_REPO`。
- 如你仍希望固定仓库，也可设置 `GITHUB_REPO=cxxCoolStar/ai-ops-example`。

### 2.2 邮件（用于发送通知）

- `SMTP_SERVER=smtp.qq.com`（按你的邮箱服务商调整）
- `SMTP_PORT=587`
- `SMTP_USER=<发件邮箱账号>`
- `SMTP_PASSWORD=<SMTP 授权码/密码>`
- `RECEIVER_EMAIL=<收件邮箱>`
- `EMAIL_ENABLED=true`（默认；本地调试不需要邮件可设为 `false`）

### 2.3 Claude（用于生成修复代码）

- `CLAUDE_COMMAND=claude`
- `CLAUDE_FIX_MODE=code_blocks`（默认）或 `agentic`
- `CLAUDE_ARGS=`（可选，给 Claude CLI 追加参数）

模式说明：
- `code_blocks`：Claude 输出 `<code_block filename="...">...</code_block>`，由系统应用到文件后提交。
- `agentic`：Claude 直接在仓库目录内修改文件（系统再做 preflight、提交、PR、邮件）。

### 2.4 Server（监听端口）

- `HTTP_HOST=127.0.0.1`
- `HTTP_PORT=8080`

### 2.5 可选：Server API Key（启用鉴权时）

- `SERVER_API_KEY=<共享 key>`

如设置了该值，则 Agent 上报时需要带 `--api-key` 或设置 `AGENT_API_KEY`。

### 2.6 Agent（上报目标仓库）

- `AGENT_REPO_URL=<需要被修复的仓库 git url>`

说明：
- Agent 上报给 Server 的 `repo_url` 默认从 `AGENT_REPO_URL` 读取，也可用 `--repo-url` 临时覆盖。
- 不同应用部署多个 Agent 时，通过各自环境变量配置不同 `AGENT_REPO_URL`。

### 2.7 可选：ELK（Agent 从 Elasticsearch 拉取错误日志）

- `ELK_URL=http://127.0.0.1:9200`
- `ELK_INDEX=filebeat-*`
- `ELK_QUERY=service.name:demo-app AND log.level:ERROR`
- `ELK_POLL_SECONDS=2`
- `ELK_SINCE_SECONDS=300`
- `ELK_BATCH_SIZE=50`

## 3. 启动服务端（Server）

在 `ai-ops` 工程目录执行：

```powershell
python scripts/server.py
```

服务端提供接口：

- 提交任务：`POST http://127.0.0.1:8080/v1/tasks`
- 查询任务：`GET  http://127.0.0.1:8080/v1/tasks/<task_id>`

## 4. 启动 Agent（监听某个日志文件）

在 `ai-ops` 工程目录执行（监控指定日志路径）：

```powershell
python scripts/agent.py `
  --log-path "C:\Users\asta1\PycharmProjects\ai-ops-example\app.log" `
  --server-url "http://127.0.0.1:8080" `
  --code-host github
```

如你希望不在命令行传 repo_url，请在环境变量里配置：

```powershell
set AGENT_REPO_URL=https://github.com/cxxCoolStar/ai-ops-example.git
```

也可以用 `--repo-url` 临时覆盖环境配置。

如果 Server 开启鉴权（设置了 `SERVER_API_KEY`），增加 `--api-key`：

```powershell
python scripts/agent.py `
  --log-path "C:\Users\asta1\PycharmProjects\ai-ops-example\app.log" `
  --server-url "http://127.0.0.1:8080" `
  --code-host github `
  --api-key "<共享key>"
```

可选：为了测试时每次都触发上报，可将去重窗口设为 0：

```powershell
python scripts/agent.py `
  --log-path "C:\Users\asta1\PycharmProjects\ai-ops-example\app.log" `
  --server-url "http://127.0.0.1:8080" `
  --code-host github `
  --dedup-window-seconds 0
```

启动后，Agent 会输出类似：

- `开始监控文件: ...app.log`
- `检测到关键词: ... ERROR ...`
- `[agent] reported error, task_id=...`

## 4.1 启动 Agent（从 ELK 拉取错误日志）

当日志由 Filebeat/Logstash 等写入 Elasticsearch 后，可以用 ELK 模式替代“监听文件”：

```powershell
set AGENT_REPO_URL=https://github.com/cxxCoolStar/ai-ops-example.git
python scripts/agent.py `
  --source elk `
  --elk-url "http://127.0.0.1:9200" `
  --elk-index "filebeat-*" `
  --elk-query "service.name:demo-app AND log.level:ERROR" `
  --server-url "http://127.0.0.1:8080" `
  --code-host github
```

## 5. 触发一次错误（写入 ERROR 日志）

在 `ai-ops-example` 目录执行：

```powershell
python app.py
```

它会在处理 `"abc"` 时触发 `ValueError` 并写入日志，Agent 监控到后会自动上报到 Server。

## 6. 查询任务状态

拿到 Agent 打印的 `task_id` 后，查询任务状态：

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/v1/tasks/<task_id>" | ConvertTo-Json
```

状态流转一般为：

- `QUEUED` → `RUNNING` → `DONE`

当完成时，返回会包含：

- `mr_url`：PR 链接（GitHub 上是 Pull Request URL）
- `trace_id`：追踪 ID

## 7. 验证 PR 与邮件

### 7.1 PR

在 Server 运行窗口中会打印：

- `PR 已创建: https://github.com/.../pull/<id>`

打开该链接确认：

- 存在修复分支
- PR diff 符合预期（例如对 `app.py` 的健壮性修复）

### 7.2 邮件

Server 会输出：

- `正在发送 HTML 修复报告邮件...`

随后在 `RECEIVER_EMAIL` 中查看是否收到邮件通知（包含 PR 链接与摘要）。

## 8. PR 评论驱动更新（再次提交到同一个 PR）

目标：当 PR 收到审查意见（评论）后，触发 Server 拉取该 PR 分支，根据评论更新代码并 push，同一个 PR 会自动更新 diff。

> 说明：GitHub Webhook 无法直接回调本机 `127.0.0.1`，本地测试推荐先走「接口直调」；如需测试 Webhook，需要使用公网隧道把本地端口暴露出去（ngrok/cloudflared 等）。

### 8.1 接口直调（本地最推荐）

前置：你已经通过上面的流程拿到 PR 链接（`mr_url`/`pr_url`）。

1) 从 PR 链接中拿到 PR 号

例如：`https://github.com/<owner>/<repo>/pull/123` 的 PR 号是 `123`。

2) 调用 PR 评论接口触发更新任务

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8080/v1/pr-comments" `
  -ContentType "application/json" `
  -Body (ConvertTo-Json @{
    repo_url   = "https://github.com/cxxCoolStar/ai-ops-example.git"
    pr_url     = "https://github.com/<owner>/<repo>/pull/<id>"
    pr_number  = 123
    comment    = "请根据审查意见更新代码：为非数字输入增加校验，并补充必要的用例。"
    code_host  = "github"
  })
```

3) 查询任务状态

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/v1/tasks/<task_id>" | ConvertTo-Json
```

当完成时，返回会包含：
- `mr_url`：仍为同一个 PR 链接
- `commit_sha`：本次更新提交的 commit
- `branch`：被更新的 PR 分支

### 8.2 GitHub Webhook（可选）

1) 配置环境变量（推荐写在 `.env`）
- `GITHUB_WEBHOOK_SECRET=<与你在 GitHub Webhook 上配置的 secret 一致>`
- `PR_COMMENT_COMMAND_PREFIX=/ai-ops`（默认值，可不设）

2) 用公网隧道把本地端口暴露出去

将 `http://127.0.0.1:8080` 暴露为一个公网 `https://...` 地址。

3) 在 GitHub 仓库配置 Webhook
- Payload URL：`https://<你的公网地址>/v1/webhooks/github`
- Content type：`application/json`
- Secret：与 `GITHUB_WEBHOOK_SECRET` 一致
- 订阅事件：`Issue comments`、`Pull request review comments`、`Pull request reviews`

4) 在 PR 下发表评论触发（默认需要前缀）

例如评论内容：
`/ai-ops 请根据审查意见更新代码：为非数字输入增加校验，并补充必要的用例。`

## 9. 常见问题排查

### 9.1 PR 创建报 422：分支没有共同历史

原因通常是创建 PR 的 `head` 分支与 `base` 分支不是同一仓库历史链路（例如误推到错误仓库、remote 配置异常）。

检查项：

- Agent 上报的 `repo_url` 是否正确
- `GITHUB_TOKEN` 是否对该仓库有 push 权限
- Server 是否根据 repo_url 解析到了正确的 `owner/repo`

### 9.2 git push 失败（exit status 128）

常见原因：

- token 权限不足
- 网络/代理导致无法访问 GitHub
- 本地 git 凭据冲突

检查项：

- `GITHUB_TOKEN` 权限与有效性
- `git` 是否可正常访问 `https://github.com`

### 9.3 Claude 返回的文件路径不正确

系统对 Claude 输出的路径做了容错（剥离 `workspaces/`、`repo/` 前缀，并尝试候选相对路径），但仍建议：

- Claude 输出 `app.py` 或仓库内真实相对路径

