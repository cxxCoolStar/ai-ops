# 端到端测试（应用日志 → ELK → Agent → Server → Claude → PR → 邮件）

本文档是“可直接照抄执行”的本机复现教程（Windows PowerShell 版本）。你将得到：
- Agent 发现 ELK 中的错误日志并上报 Server（输出 `task_id`）
- Server 自动生成修复、push 分支、创建 PR（返回 `mr_url`）
- Server 发送邮件通知（SMTP）

## 0. 你需要准备什么

### 0.1 软件

在 PowerShell 执行以下命令，确保都能正常输出版本号：

```powershell
python --version
git --version
claude --version
```

### 0.2 Python 依赖

在 `ai-ops` 工程目录执行（仅第一次需要）：

```powershell
pip install watchdog python-dotenv PyGithub
```

### 0.3 外部依赖

- GitHub：需要一个 PAT（能 push 分支 + 创建 PR）
- SMTP：需要能发邮件（用户名/授权码/收件人）
- Elasticsearch：能查询到 Filebeat 写入的日志（本文假设索引为 `filebeat-*`）

## 1. 准备两个仓库

### 1.1 AI-Ops（本仓库）

假设你已经在：

`C:\Users\asta1\PycharmProjects\ai-ops`

### 1.2 被修复目标仓库（ai-ops-example）

目标仓库用于被 Server clone、修改、推分支、提 PR：

```powershell
cd C:\Users\asta1\PycharmProjects
git clone https://github.com/cxxCoolStar/ai-ops-example.git
```

## 2. 配置 `.env`（一次配好，后面都不用改）

在 `C:\Users\asta1\PycharmProjects\ai-ops\.env` 写入下面内容（按你的实际值替换尖括号部分）：

```dotenv
CODE_HOST=github

GITHUB_TOKEN=<YOUR_GITHUB_TOKEN>
AGENT_REPO_URL=https://github.com/cxxCoolStar/ai-ops-example.git

SMTP_SERVER=smtp.qq.com
SMTP_PORT=587
SMTP_USER=<YOUR_SMTP_USER>
SMTP_PASSWORD=<YOUR_SMTP_PASSWORD_OR_APP_TOKEN>
RECEIVER_EMAIL=<YOUR_RECEIVER_EMAIL>
EMAIL_ENABLED=true

HTTP_HOST=127.0.0.1
HTTP_PORT=8080

CLAUDE_COMMAND=claude
CLAUDE_FIX_MODE=code_blocks

ELK_URL=http://127.0.0.1:9200
ELK_INDEX=filebeat-*
ELK_QUERY=service.name:demo-app AND log.level:ERROR
ELK_POLL_SECONDS=1
ELK_SINCE_SECONDS=300
ELK_BATCH_SIZE=50
```

## 3. 验证 ELK 已可用（非常关键）

在 `ai-ops` 工程目录执行：

```powershell
Invoke-RestMethod "http://127.0.0.1:9200/" | ConvertTo-Json -Depth 5
```

你应该看到包含 `version` 等字段的 JSON（代表 Elasticsearch 可访问）。

再检查是否能查到 `filebeat-*` 的索引：

```powershell
Invoke-RestMethod "http://127.0.0.1:9200/_cat/indices/filebeat-*?v"
```

如果这里为空，说明你的 ELK 采集（Filebeat/Logstash）还没把日志写入 ES，需要先把“应用日志文件 → ES”打通再继续。

## 4. 启动 Server（监听任务并编排修复）

打开一个 PowerShell，进入 `ai-ops` 目录：

```powershell
cd C:\Users\asta1\PycharmProjects\ai-ops
python scripts/server.py
```

看到 Server 持续运行即可（不要关）。

## 5. 启动 Agent（从 ELK 拉取错误并上报 Server）

再打开一个 PowerShell，进入 `ai-ops` 目录：

```powershell
cd C:\Users\asta1\PycharmProjects\ai-ops
python scripts/agent.py `
  --source elk `
  --server-url "http://127.0.0.1:8080" `
  --code-host github `
  --dedup-window-seconds 0
```

你应该看到类似输出：
- `[agent] repo_url: https://github.com/cxxCoolStar/ai-ops-example.git`
- `[agent] source=elk`

## 6. 触发一条错误日志（让它进入 ELK）

这里的关键不是“应用怎么报错”，而是“错误日志最终要进 Elasticsearch”。下面给一个最直接的可执行示例：使用本仓库自带 demo 服务产生 ERROR（会写入 JSON 日志）。

打开一个 PowerShell：

```powershell
cd C:\Users\asta1\PycharmProjects\ai-ops
python examples/app.py --port 9030 --tick-seconds 999 --tick-mode ok
```

再开一个 PowerShell，发起请求触发错误：

```powershell
Invoke-RestMethod "http://127.0.0.1:9030/api/parse-int?value=abc" | ConvertTo-Json
```

然后用下面命令确认 Elasticsearch 里已经有这条 ERROR：

```powershell
$body = @{
  size = 1
  sort = @(@{ '@timestamp' = 'desc' }, @{ 'event.id' = 'desc' })
  query = @{
    bool = @{
      must = @(@{ query_string = @{ query = 'service.name:demo-app AND log.level:ERROR' } })
      filter = @(@{ range = @{ '@timestamp' = @{ gte = 'now-5m' } } })
    }
  }
} | ConvertTo-Json -Depth 30

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9200/filebeat-*/_search" -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 8
```

如果能看到 `hits.hits[0]._source.log.level = "ERROR"`，说明“应用日志 → ELK”成功。

## 7. 等待 Agent 上报并拿到 task_id

回到 Agent 的窗口，你应该会看到：

`[agent] reported error, task_id=<uuid>`

把这个 `task_id` 复制下来。

## 8. 查询任务状态（直到 DONE）

在任意 PowerShell 执行（把 `<task_id>` 替换掉）：

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/v1/tasks/<task_id>" | ConvertTo-Json -Depth 10
```

你会看到状态流转：
- `QUEUED` → `RUNNING` → `DONE`

当 `DONE` 时，响应里会包含：
- `mr_url`：PR 链接
- `trace_id`：本次修复的 trace

## 9. 验证 PR 与邮件

### 9.1 PR

打开 `mr_url`，你应该能看到类似：

`https://github.com/cxxCoolStar/ai-ops-example/pull/<number>`

### 9.2 邮件

在 Server 窗口中，你应该能看到“发送邮件”的日志；同时去 `RECEIVER_EMAIL` 收件箱检查是否收到带 PR 链接的通知邮件。

## 10. 常见失败点（按出现顺序排查）

### 10.1 ES 查询不到 filebeat 索引

- 先跑通“应用日志文件 → Filebeat/Logstash → Elasticsearch”
- 只要第 3 步的 `_cat/indices/filebeat-*` 没结果，后面 Agent/Server 都无法工作

### 10.2 Agent 能查到 ES，但一直不输出 task_id

- 把 `ELK_QUERY` 改宽松验证：`ELK_QUERY=log.level:ERROR`
- 把 `ELK_SINCE_SECONDS` 临时改大：例如 `3600`

### 10.3 任务卡在 RUNNING 很久

- 重点看 Server 窗口是否卡在 Claude 调用阶段
- 用 `GET /v1/tasks/<task_id>` 看 `workspace_dir`，必要时去该目录查看 clone 的 repo 是否正常

