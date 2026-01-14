import os
import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ai_ops import config


class LogFileHandler(FileSystemEventHandler):
    def __init__(self, file_path, callback):
        self.file_path = os.path.abspath(file_path)
        self.callback = callback
        self.last_position = self._get_file_size()
        self.debounce_seconds = getattr(config, "DEBOUNCE_SECONDS", 2.0)
        self._buffer_lines = []
        self._armed = False
        self._last_update_ts = 0.0
        self._lock = threading.Lock()
        print(f"开始监控文件: {self.file_path}, 当前指针: {self.last_position}")
        self._start_flush_loop()

    def _get_file_size(self):
        if os.path.exists(self.file_path):
            return os.path.getsize(self.file_path)
        return 0

    def on_modified(self, event):
        if os.path.abspath(event.src_path) == self.file_path:
            self._process_new_lines()

    def _process_new_lines(self):
        current_size = self._get_file_size()
        if current_size < self.last_position:
            print("日志文件被截断，重置指针")
            self.last_position = 0
            with self._lock:
                self._buffer_lines = []
                self._armed = False
                self._last_update_ts = 0.0

        if current_size > self.last_position:
            with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()
                self._check_for_errors(new_lines)

    def _check_for_errors(self, lines):
        if not lines:
            return

        with self._lock:
            self._buffer_lines.extend(lines)
            for line in lines:
                if any(kw in line for kw in config.KEYWORDS):
                    self._armed = True
                    self._last_update_ts = time.time()
                    print(f"检测到关键词: {line.strip()}")
                    break

    def _start_flush_loop(self):
        def loop():
            while True:
                time.sleep(0.2)
                self._flush_if_ready()

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()

    def _flush_if_ready(self):
        with self._lock:
            if not self._armed:
                return
            if (time.time() - self._last_update_ts) < self.debounce_seconds:
                return
            full_error = "".join(self._buffer_lines)
            self._buffer_lines = []
            self._armed = False
            self._last_update_ts = 0.0

        if full_error.strip():
            self.callback(full_error)


def start_monitoring(file_path, callback):
    event_handler = LogFileHandler(file_path, callback)
    observer = Observer()
    observer.schedule(
        event_handler,
        path=os.path.dirname(os.path.abspath(file_path)),
        recursive=False,
    )
    observer.start()
    return observer

