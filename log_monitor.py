import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config

class LogFileHandler(FileSystemEventHandler):
    def __init__(self, file_path, callback):
        self.file_path = os.path.abspath(file_path)
        self.callback = callback
        self.last_position = self._get_file_size()
        print(f"开始监控文件: {self.file_path}, 当前指针: {self.last_position}")

    def _get_file_size(self):
        if os.path.exists(self.file_path):
            return os.path.getsize(self.file_path)
        return 0

    def on_modified(self, event):
        if event.src_path == self.file_path:
            self._process_new_lines()

    def _process_new_lines(self):
        current_size = self._get_file_size()
        if current_size < self.last_position:
            # 文件被清空或截断
            print("日志文件被截断，重置指针")
            self.last_position = 0

        if current_size > self.last_position:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()
                
                self._check_for_errors(new_lines)

    def _check_for_errors(self, lines):
        # 简单策略：只要这批新日志里有 Error，就把这批（以及可能的上下文）都发过去
        # 改进：如果 Error 位于最后一行，可能 Traceback 还没写完，这里暂时简化处理：
        # 只要发现关键词，就将整块 capture 下来。
        
        found_error = False
        for line in lines:
            if any(kw in line for kw in config.KEYWORDS):
                found_error = True
                print(f"检测到关键词: {line.strip()}")
                break # 只要发现这一批里有错误，就全部发送，保留完整上下文
        
        if found_error:
            # 将所有读取到的新行合并，作为错误上下文
            full_error = "".join(lines)
            self.callback(full_error)

def start_monitoring(file_path, callback):
    event_handler = LogFileHandler(file_path, callback)
    observer = Observer()
    # 监控所在目录
    observer.schedule(event_handler, path=os.path.dirname(os.path.abspath(file_path)), recursive=False)
    observer.start()
    return observer

if __name__ == "__main__":
    def dummy_callback(content):
        print(f"回调触发，错误内容:\n{content}")
    
    # 确保文件存在
    if not os.path.exists(config.LOG_FILE_PATH):
        with open(config.LOG_FILE_PATH, 'w') as f:
            f.write("Log initialized\n")
            
    obs = start_monitoring(config.LOG_FILE_PATH, dummy_callback)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
