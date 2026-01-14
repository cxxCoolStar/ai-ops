# 方案：GitLab 优先支持 + 流程追踪（先 1 再 2 再 3）

## 0. 背景与目标

当前系统已具备：日志触发 → Claude 生成结构化变更（code_block）→ 本地应用 → 编译检查 → 推送分支 → 创建 PR/MR → 邮件通知 的基础链路。

本方案聚焦：

1) 优先支持公司 GitLab：能够拉取代码、创建分支、提交、推送，并创建 GitLab MR（用户习惯上说 PR，这里统一称 MR）。
2) 在 GitLab 支持稳定后，再做 HTTP 接口（输入 GitLab 地址 + 报错，自动下载 codebase 并分析/修复）。
3) 最后建立问题库：保存一次修复流程的数据，支持相似问题检索与方案复用。

本文件用于“追踪流程”的统一设计与后续扩展的接口约束，不涉及代码实现细节。

---

## 1. 阶段路线（建议）

### Phase A：GitLab 支持（优先做）

目标：
- 支持 GitLab 仓库 URL（含自建域名）解析
- 支持克隆/拉取到本地工作区
- 支持创建修复分支、提交、推送
- 支持创建 MR 并拿到 MR 链接
- 最小安全：Token 不入日志，不回显

交付标准：
- 输入：repo_url、gitlab_token、error_content、（可选）base_branch
- 输出：mr_url、trace_id、最终状态（success/fail）与失败原因

### Phase B：HTTP 接口（第二做）

目标：
- 提供一个 HTTP 入口，将 repo_url + error_content 变成异步任务
- Worker 侧复用 Phase A 的 GitLab 流程
- 提供任务状态查询与追踪信息回放

交付标准：
- 任务 API：提交/查询/取消（可选）
- 资源治理：并发上限、超时、最大仓库大小/文件数限制

### Phase C：问题库（最后做）

目标：
- 把每一次修复的输入/输出/中间产物落库
- 根据“错误指纹 + 语义”检索历史相似问题
- 命中后：优先推荐已验证方案，或注入到 Claude 提示词里减少发散

交付标准：
- 能按 error_signature 查询命中
- 能按关键词/堆栈帧/文件路径筛选
- 能回放某次修复的关键上下文与最终变更

---

## 2. 模块边界（抽象层）

为支持多平台（GitLab/GitHub/…），建议拆为两层：

### 2.1 VCS 工作区层（纯 Git，不关心平台）

职责：
- clone/fetch/checkout/status/add/commit/push
- 维护工作目录、清理
- 提供“本次任务产生了哪些文件变更”的可观测能力（供追踪模块记录）

输入输出：
- 输入：repo_url、token（通过安全方式注入）、work_dir、branch_name、commit_message
- 输出：git 结果（stdout/stderr/returncode）、commit_sha、变更摘要

### 2.2 托管平台层（GitLab API）

职责：
- 解析 GitLab repo_url（含 group/subgroup/project）
- 获取默认分支（如果未指定）
- 创建 MR：head=branch，base=default_branch，title/body
- 可选：添加标签、指派人、评论、CI 状态查询

输入输出：
- 输入：repo 标识、token、branch、title/body
- 输出：mr_url、mr_iid、web_url

---

## 3. GitLab 关键设计点（Phase A）

### 3.1 Repo URL 支持范围

需要支持至少两种：
- HTTPS：`https://gitlab.company.com/group/subgroup/project.git`
- SSH：`git@gitlab.company.com:group/subgroup/project.git`

建议统一内部 repo 表示：
- host（gitlab.company.com）
- project_path（group/subgroup/project）
- project_id（可选，通过 API 查询后缓存）

### 3.2 鉴权策略

优先支持：
- GitLab Personal Access Token（PAT）

注意：
- Git clone/push 的 token 注入需要避免写入远端 URL 的持久化配置（避免残留在 `.git/config` 或日志）。
- 追踪系统不得记录明文 token。

### 3.3 MR（PR）创建约定

统一命名：
- 分支：`fix/ai-<timestamp>-<short_sig>`
- MR 标题：`[AI Fix] <error_summary>`
- MR 描述：包含 trace_id、错误摘要、修复摘要、验证结果

---

## 4. 流程追踪（核心：Phase A 就要落地）

### 4.1 追踪目标

追踪不是“日志打印”，而是可检索、可回放、可统计的结构化数据，用于：
- 诊断：失败发生在哪一步、为什么失败
- 审计：哪些文件被改了、提交了什么、MR 链接是什么
- 复用：相似问题检索与方案复用（Phase C）

### 4.2 Trace 概念与粒度

**Trace（一次修复任务）**：从接到 error_content 到 MR 创建/失败为止的全链路记录。

建议每次任务生成：
- `trace_id`：UUID 或 时间戳+随机串
- `error_signature`：对错误内容标准化后的 hash（用于去重与检索）
- `repo_fingerprint`：host + project_path + base_branch（用于跨项目区分）

### 4.3 状态机（建议的步骤枚举）

每个 Trace 走一组 Step（可扩展）：

1) `RECEIVED`：收到输入（repo_url + error_content）
2) `PREPARE_WORKDIR`：准备工作目录、清理旧任务
3) `CLONE_OR_FETCH`：拉取仓库
4) `CHECKOUT_BASE`：切到 base_branch 并同步
5) `CREATE_FIX_BRANCH`：创建修复分支
6) `AI_PROPOSE_PATCH`：Claude 生成 code_blocks
7) `APPLY_PATCH`：本地应用 code_blocks
8) `PREFLIGHT_CHECK`：编译检查/（未来）单测
9) `GIT_COMMIT`：提交
10) `GIT_PUSH`：推送
11) `CREATE_MR`：GitLab 创建 MR
12) `NOTIFY`：邮件/IM 通知
13) `CLEANUP`：可选，清理工作目录
14) `DONE`：成功结束

失败时：
- `FAILED`：记录失败 step、错误类型、错误信息、（可选）stderr 摘要

### 4.4 需要保存的数据结构（最小集合）

#### Trace 表（一次任务）
- trace_id
- created_at / finished_at
- repo_url（脱敏：可保留 host + project_path，去掉 userinfo/token）
- base_branch / fix_branch
- error_signature
- error_excerpt（截断存储，避免过大）
- status（DONE/FAILED）
- failure_step（如 FAILED）
- failure_message（如 FAILED）
- mr_url（如 DONE）
- commit_sha（如 DONE）

#### Step 表（步骤流水）
- trace_id
- step_name
- started_at / finished_at
- status（OK/FAIL）
- message（简短摘要）
- artifacts_ref（可选：指向 artifact 表）

#### Artifact 表（中间产物索引，建议只存摘要）
- trace_id
- type（AI_OUTPUT / DIFF_SUMMARY / CHECK_OUTPUT / GIT_STDERR 等）
- content_excerpt（截断）
- content_path（可选：落文件时的路径索引）

#### Change 表（文件变更摘要）
- trace_id
- file_path
- change_type（modified/created/deleted）
- before_hash / after_hash（可选）
- size_delta（可选）

### 4.5 存储选型（建议）

Phase A/B（验证期）：
- SQLite 即可（部署简单）

Phase B/C（服务化/多实例）：
- PostgreSQL（稳定、可扩展）
- 若后续做语义检索：PostgreSQL + pgvector 或独立向量库（到 Phase C 再评估）

---

## 5. 为 Phase B（HTTP）预留的接口约束

即使 Phase B 还没做，Phase A 的“流程引擎”建议就按“可被 API 调用”的方式组织：
- 输入 DTO：repo_url、token_ref、error_content、options（base_branch、timeout、max_repo_size 等）
- 输出 DTO：trace_id、status、mr_url、failure_step、failure_message

并且追踪数据应做到：
- 任何一步失败都能通过 trace_id 查询到失败位置与关键信息

---

## 6. 为 Phase C（问题库）预留的检索策略

### 6.1 相似问题检索（先规则后语义）

第一阶段（规则）：
- error_signature 精确命中
- 堆栈帧/异常类型/关键文件路径的组合检索

第二阶段（语义）：
- 对 error_summary、stacktrace、fix_summary 做 embedding
- topK 检索相似 trace，并返回已验证 MR/commit 作为参考

### 6.2 命中后的动作（建议）

优先顺序：
1) 若命中“同仓库同路径同异常”且有成功记录：直接复用已验证修复步骤作为提示上下文
2) 否则：将历史方案注入 Claude prompt（作为约束，不自动应用旧补丁）

---

## 7. 风险清单（GitLab 优先阶段就要管）

- Token 泄露：禁止打印；repo_url 持久化前必须脱敏
- 大仓库拉取：限制大小、文件数、超时；必要时 shallow clone
- 并发与隔离：每个 trace 独立 workdir，防止互相污染
- 提交质量：至少 compileall；后续逐步加单测/静态检查

---

## 8. 验收清单（Phase A 完成的判定）

- 能对 GitLab repo 成功 clone → 创建分支 → 提交 → push
- 能通过 GitLab API 创建 MR 并返回 MR 链接
- 任意一步失败都有 trace_id，且可查询失败 step 与摘要信息
- 追踪数据不包含明文 token/密码

