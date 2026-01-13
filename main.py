import time
import os
import config
from log_monitor import start_monitoring
from claude_interface import ClaudeInterface
from email_service import EmailSender

def main():
    print("AI Ops 错误报告系统启动中...")
    
    # 初始化组件
    claude = ClaudeInterface()
    email = EmailSender()
    
    # 确保日志文件存在
    log_path = os.path.abspath(config.LOG_FILE_PATH)
    if not os.path.exists(log_path):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"--- 系统启动于 {time.ctime()} ---\n")
    
    def process_error(error_content):
        print("正在获取 Claude 分析结果...")
        analysis = claude.analyze_error(error_content)
        
        print("正在发送分析报告...")
        subject = f"【系统告警】检测到关键错误 - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        body = f"检测到以下日志错误：\n\n{error_content}\n\n"
        body += "--- Claude AI 分析过程与建议 ---\n\n"
        body += "Claude Code 正在读取本地代码并分析...\n\n"
        body += analysis
        
        email.send_email(subject, body)
        print("处理完成。")

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
