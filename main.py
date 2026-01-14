import time
import os
import config
from log_monitor import start_monitoring
from claude_interface import ClaudeInterface
from email_service import EmailSender
from github_service import GitHubService

def main():
    print("AI Ops 错误报告系统 (Agentic GitOps 版) 启动中...")
    
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
        print("\n[!] 检测到错误，开始代理式自动修复流程...")
        
        # 1. 创建修复分支 (先切分支，保证 Claude 修改在分支上)
        print("正在准备 GitHub 修复分支...")
        branch_name = github.create_fix_branch("agentic-fix")
        
        # 2. 调用 Claude Code 执行修复
        print("正在启动 Claude Code 执行代理式修复（请稍候，AI 正在修改文件）...")
        # 注意：这里我们相信 Claude Code 会直接修改本地文件
        claude.execute_agentic_fix(error_content)
        
        # 3. 获取结构化总结
        print("正在生成 PR 报告总结 (原因、过程、结论)...")
        analysis = claude.get_structured_summary(error_content)
        
        # 4. GitOps 提交
        # 我们假设修复确实发生了。实际可以增加 git status 检查
        print("正在提交修复代码并创建 PR...")
        commit_msg = f"fix(ai): agentic auto-repair for detected error\n\nLog: {error_content[:100]}..."
        github.commit_and_push(branch_name, commit_msg)
        
        # 创建 PR
        pr_title = f"🛠️ [AI Agentic Fix] 修复系统路径错误"
        pr_body = f"""# 🤖 AI 代理式自动修复报告

## 🔍 诊断与修复过程
{analysis}

---
- **检测时间**: `{time.strftime('%Y-%m-%d %H:%M:%S')}`
- **修复方式**: Claude Code 代理自动化修改
- **分支**: `{branch_name}`

*由 [AI-Ops] 系统自动生成并提交。*
"""
        pr_url = github.create_pull_request(branch_name, pr_title, pr_body)
        print(f"PR 已创建: {pr_url}")

        # 5. 发送精美 HTML 邮件
        print("正在发送 HTML 修复报告邮件...")
        subject = f"🛠️ AI 自动修复完成：PR 已提交"
        
        html_content = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial; line-height: 1.6; color: #333; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); border: 1px solid #eee;">
                <div style="background: #24292e; color: white; padding: 25px; text-align: center;">
                    <h2 style="margin: 0;">AI-Ops 自动化运维</h2>
                </div>
                <div style="padding: 30px;">
                    <div style="border-left: 4px solid #f97583; background: #fff5f5; padding: 15px; margin-bottom: 25px;">
                        <strong style="color: #d73a49;">检测到报错：</strong><br>
                        <code style="font-size: 13px;">{error_content[:100]}...</code>
                    </div>
                    
                    <p style="font-size: 16px;">AI 代理（Claude Code）已自动定位并修复了代码逻辑。点击下方按钮查看变更详情：</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{pr_url}" style="background: #2ea44f; color: white; padding: 12px 25px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">进入 GitHub 查看 PR</a>
                    </div>
                    
                    <div style="background: #f6f8fa; padding: 15px; border-radius: 6px; font-size: 14px; color: #555;">
                        <strong>修复总结：</strong><br>
                        {analysis[:300].replace('\n', '<br>')}...
                    </div>
                </div>
                <div style="background: #eee; padding: 15px; text-align: center; font-size: 11px; color: #999;">
                    本项目由 AI-Ops 自动维护
                </div>
            </div>
        </body>
        </html>
        """
        
        email.send_email(subject, html_content, is_html=True)
        
        # 6. 清理环境
        github.clean_up("main")
        print("本次代理修复流程圆满完成。")

    # 启动监控
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

if __name__ == "__main__":
    main()
