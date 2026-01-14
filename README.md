# AI-Ops（Agentic GitOps 自动修复系统）

AI-Ops 是一个在本地或私有环境运行的“自动化运维修复”系统：它监听应用日志，检测错误后调用 Claude 进行代码修复，然后以 GitOps 的方式提交到代码托管平台（GitHub/GitLab），并通过邮件通知审核合并。

## 功能特性
- 实时日志监听（Agent）
- 错误收集与去重（关键词触发 + 指纹）
- Claude 修复两种模式：
  - code_blocks：输出结构化 `<code_block>`，由系统应用到文件
  - agentic：Claude 直接在仓库工作目录内修改文件
- GitOps 工作流：创建修复分支、提交、推送、PR/MR
- 邮件通知：发送修复摘要与 PR 链接
- 追踪存储：SQLite 记录 trace 与步骤状态

## 目录结构
- `ai_ops/` 项目主包
  - `agent/agent.py` Agent 客户端
  - `server/http_server.py` 服务端（任务接收与编排）
  - `core/orchestrator.py` 修复流程编排
  - `monitoring/log_monitor.py` 日志监听
  - `integrations/` Claude 与邮件
  - `vcs/` Git 操作与 GitHub/GitLab 接口
  - `trace/trace_store.py` 追踪存储
  - `workspace/workspace_manager.py` 工作区管理
- `scripts/` 启动脚本
  - `server.py` 启动服务端
  - `agent.py` 启动 Agent
  - `local_monitor.py` 单机本地监控模式
- `examples/app.py` 示例应用（用于产生错误日志）
- `doc/e2e-test.md` 端到端测试步骤

## 安装依赖
系统依赖：
- Python 3.10+
- Git
- Claude CLI（`CLAUDE_COMMAND` 对应的可执行命令）
- 可选：`watchdog`、`python-dotenv`、`PyGithub`

Python 依赖（示例）：
```bash
pip install watchdog python-dotenv PyGithub
```

## 配置
支持 `.env` 或系统环境变量，关键项如下：
- 基础
  - `CODE_HOST=github` 或 `gitlab`
  - `LOG_FILE_PATH`（本地模式使用）
- Claude
  - `CLAUDE_COMMAND=claude`
  - `CLAUDE_FIX_MODE=code_blocks`（默认）或 `agentic`
  - `CLAUDE_ARGS=`（附加 CLI 参数）
- GitHub
  - `GITHUB_TOKEN`（PAT，需 push/PR 权限）
  - `GITHUB_REPO`（可选；server 会从 `repo_url` 自动解析）
- GitLab
  - `GITLAB_BASE_URL`、`GITLAB_TOKEN`、`GITLAB_PROJECT`
- Server
  - `HTTP_HOST=127.0.0.1`
  - `HTTP_PORT=8080`
  - `SERVER_API_KEY`（可选，启用 API 鉴权）
- 邮件
  - `SMTP_SERVER`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`
  - `RECEIVER_EMAIL`

## 快速开始
1) 启动服务端
```powershell
python scripts/server.py
```

2) 启动 Agent（监听某个日志文件）
```powershell
python scripts/agent.py `
  --log-path "C:\Users\asta1\PycharmProjects\ai-ops-example\app.log" `
  --repo-url "https://github.com/cxxCoolStar/ai-ops-example.git" `
  --server-url "http://127.0.0.1:8080" `
  --code-host github
```

3) 触发错误（写日志）
```powershell
python examples/app.py
```

4) 查询任务状态
```powershell
Invoke-RestMethod "http://127.0.0.1:8080/v1/tasks/<task_id>" | ConvertTo-Json
```

更多细节：请见 [doc/e2e-test.md](file:///c:/Users/asta1/PycharmProjects/ai-ops/doc/e2e-test.md)

## 模式说明
- code_blocks：稳定、可控、适合最小变更与审计
- agentic：Claude 直接编辑仓库，适合多文件联动与复杂改动
切换方式：
```powershell
set CLAUDE_FIX_MODE=agentic
```

## 常见问题排查
- PR 422“没有共同历史”：校验 `repo_url`、token 权限、remote 配置；必要时在 clone 后 `fetch` 并 checkout 默认分支再切分支
- git push 128：检查 token 权限、网络连通性、本地 git 凭据冲突
- Claude 路径不正确：系统已做容错（剥离 workspaces/repo 等前缀，尝试候选相对路径），仍建议输出仓库内真实相对路径或直接文件名


