import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config

class EmailSender:
    def __init__(self):
        self.server = config.SMTP_SERVER
        self.port = config.SMTP_PORT
        self.user = config.SMTP_USER
        self.password = config.SMTP_PASSWORD

    def send_email(self, subject, body, is_html=False):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.user
            msg['To'] = config.RECEIVER_EMAIL
            msg['Subject'] = subject

            content_type = 'html' if is_html else 'plain'
            msg.attach(MIMEText(body, content_type, 'utf-8'))

            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
            print(f"邮件已发送至: {config.RECEIVER_EMAIL}")
            return True
        except Exception as e:
            print(f"发送邮件失败: {e}")
            return False

if __name__ == "__main__":
    # 简单测试
    sender = EmailSender()
    # sender.send_email("测试邮件", "这是一条来自系统的测试信息。")
