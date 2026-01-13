import time
import os

LOG_FILE = "app.log"

def write_log(message):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    print(f"已写入日志: {message}")

if __name__ == "__main__":
    print("开始模拟日志写入...")
    write_log("INFO: 应用程序已启动")
    time.sleep(2)
    write_log("DEBUG: 正在进行数据处理...")
    time.sleep(2)
    write_log("ERROR: 发生了未知错误 - ValueError: invalid literal for int() with base 10: 'abc'")
    time.sleep(2)
    write_log("INFO: 写入完成。")
