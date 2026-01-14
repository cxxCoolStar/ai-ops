import time
import os
import config
from log_monitor import start_monitoring
from claude_interface import ClaudeInterface
from email_service import EmailSender
from github_service import GitHubService

def main():
    print("AI Ops 错误报告系统 (GitOps 版) 启动中...")
    
    # 初始化组件
    claude = ClaudeInterface()
    email = EmailSender()
    github = GitHubService()
    
    # 确保日志文件存在
    log_path = os.path.abspath(config.LOG_FILE_PATH)
    if not os.path.exists(log_path):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"--- 系统启动于 {time.ctime()} ---\n")
    
    def process_error(error_content):
        print("\n[!] 检测到错误，开始自动修复流程...")
        
        # 1. 获取分析结果
        print("正在获取 Claude 分析建议与修复代码...")
        analysis = claude.analyze_error(error_content)
        
        # 2. 自动化 GitOps 流程
        print("正在准备 GitHub PR...")
        # 创建修复分支
        branch_name = github.create_fix_branch("auto-fix")
        
        # 应用修复
        applied_files = claude.extract_and_apply_fix(analysis)
        
        if applied_files:
            # 提交并推送
            commit_msg = f"fix(ai): auto-repair for detected error\n\nLog: {error_content[:100]}..."
            github.commit_and_push(branch_name, commit_msg)
            
            # 创建 PR
            pr_title = f"🛠️ [AI Auto-Repair] 修复 {error_content[:30]}..."
            
            # 构建详细的 PR 描述
            pr_body = f"""# AI 自动修复报告

## 🔍 问题诊断
发现于: `{time.strftime('%Y-%m-%d %H:%M:%S')}`

### 错误详情
```
{error_content}
```

## 💡 解决思路
{analysis}

## 🚀 修复说明
- 自动识别错误模式并应用最佳实践修复。
- 创建了独立修复分支: `{branch_name}`。

---
*由 [AI-Ops] 系统自动生成并提交。*
"""
            pr_url = github.create_pull_request(branch_name, pr_title, pr_body)
            
            print(f"PR 已创建: {pr_url}")
            
            # 3. 发送邮件通知
            subject = f"【故障自动修复】PR 已提交：修复检测到的运行时错误"
            body = f"""### 📢 系统告警：检测到关键错误并已启动自动修复

**错误快照：**
```
{error_content}
```

**🚀 自动修复进展：**
GitHub PR 已创建: {pr_url}

---

### 🧠 Claude 分析报告

#### 问题原因
{analysis}

#### 修复说明
- **分支**: `{branch_name}`
- **修改文件**: {", ".join(applied_files)}

请点击上方 PR 链接进行代码审查与合并。
"""
            email.send_email(subject, body)
            
            # 4. 回到主分支（保持环境整洁）
            github.clean_up("main") 
        else:
            print("未能提取到有效的修复代码，仅发送分析邮件。")
            subject = f"【系统告警】检测到错误 (未生成修复) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            email.send_email(subject, f"日志错误：\n\n{error_content}\n\n分析建议：\n\n{analysis}")
            
        print("本次错误处理完成。")

    # 开启监控
    observer = start_monitoring(log_path, process_error)
    
    try:
        print(f"正在监控: {log_path}")
        print("按 Ctrl+C 停止运行。")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止系统...")
        observer.stop()
    observer.join()
    print("系统已退出。")

if __name__ == "__main__":
    main()
