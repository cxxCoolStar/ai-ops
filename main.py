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
            pr_title = "🛠️ [AI Auto-Repair] 自动检测并修复运行错误"
            pr_body = f"## 错误分析\n{analysis}\n\n---\n*由 AI 运维系统自动生成*"
            pr_url = github.create_pull_request(branch_name, pr_title, pr_body)
            
            print(f"PR 已创建: {pr_url}")
            
            # 3. 发送邮件通知
            subject = f"【系统修复建议】已创建 PR 修复错误 - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            body = f"检测到以下日志错误：\n\n{error_content}\n\n"
            body += f"🚀 **Claude 已自动生成修复 PR**：\n{pr_url}\n\n"
            body += "--- 分析详情 ---\n\n"
            body += analysis
            
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
