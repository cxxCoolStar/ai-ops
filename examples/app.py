import argparse
import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name, environment):
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record):
        payload = {
            "@timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "log.level": record.levelname,
            "message": record.getMessage(),
            "service.name": self.service_name,
            "service.environment": self.environment,
            "process.pid": record.process,
            "thread.name": record.threadName,
            "event.id": getattr(record, "event_id", ""),
            "request.id": getattr(record, "request_id", ""),
        }
        if record.exc_info:
            payload["error.stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def build_logger(log_path, service_name, environment, level="INFO"):
    logger = logging.getLogger("demo_app")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = JsonFormatter(service_name=service_name, environment=environment)

    os.makedirs(os.path.dirname(os.path.abspath(log_path)) or ".", exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def parse_int(value):
    if not isinstance(value, (int, float, str)):
        raise TypeError(f"Expected int, float, or str, got {type(value).__name__}")
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("Cannot parse empty string to int")
        if not value.lstrip('-').isdigit():
            raise ValueError(f"Invalid literal for int(): '{value}'")
    return int(value)


def divide(a, b):
    return parse_int(a) / parse_int(b)


def ingest_user(payload):
    user_id = parse_int(payload["user_id"])
    age = parse_int(payload["age"])
    return {"user_id": user_id, "age": age}


def do_work(logger, mode, request_id):
    event_id = str(uuid.uuid4())
    extra = {"event_id": event_id, "request_id": request_id}
    logger.info("work.start", extra=extra)

    if mode == "value_error":
        try:
            parse_int("abc")
        except Exception:
            logger.error("work.failed", exc_info=True, extra=extra)
            raise
    elif mode == "zero_div":
        try:
            divide("1", "0")
        except Exception:
            logger.error("work.failed", exc_info=True, extra=extra)
            raise
    elif mode == "no_exception_error":
        logger.error("work.error_without_exception", extra=extra)
    elif mode == "java_like":
        msg = "\n".join(
            [
                'Exception in thread "main" java.lang.NullPointerException: boom',
                "\tat com.example.demo.App.handle(App.java:42)",
                "\tat com.example.demo.App.main(App.java:10)",
                "Caused by: java.lang.IllegalArgumentException: bad input",
                "\tat com.example.demo.Parser.parse(Parser.java:7)",
            ]
        )
        logger.error(msg, extra=extra)
    elif mode == "spam_info":
        for i in range(200):
            logger.info(f"work.noise i={i}", extra=extra)
    else:
        logger.info("work.ok", extra=extra)

    logger.info("work.end", extra=extra)
    return event_id


class DemoHandler(BaseHTTPRequestHandler):
    logger = None
    default_mode = "value_error"

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
            return
        if parsed.path == "/api/parse-int":
            qs = parse_qs(parsed.query or "")
            value = (qs.get("value") or [""])[0]
            request_id = (qs.get("request_id") or [str(uuid.uuid4())])[0]
            event_id = str(uuid.uuid4())
            extra = {"event_id": event_id, "request_id": request_id}
            self.logger.info("api.parse_int.start", extra=extra)
            try:
                result = parse_int(value)
                self.logger.info("api.parse_int.ok", extra=extra)
                self._send(200, json.dumps({"ok": True, "result": result, "event_id": event_id}, ensure_ascii=False))
            except Exception as e:
                self.logger.error("api.parse_int.failed", exc_info=True, extra=extra)
                self._send(200, json.dumps({"ok": False, "error": str(e), "event_id": event_id, "http_status": 500}, ensure_ascii=False))
            return
        if parsed.path == "/api/divide":
            qs = parse_qs(parsed.query or "")
            a = (qs.get("a") or [""])[0]
            b = (qs.get("b") or [""])[0]
            request_id = (qs.get("request_id") or [str(uuid.uuid4())])[0]
            event_id = str(uuid.uuid4())
            extra = {"event_id": event_id, "request_id": request_id}
            self.logger.info("api.divide.start", extra=extra)
            try:
                result = divide(a, b)
                self.logger.info("api.divide.ok", extra=extra)
                self._send(200, json.dumps({"ok": True, "result": result, "event_id": event_id}, ensure_ascii=False))
            except Exception as e:
                self.logger.error("api.divide.failed", exc_info=True, extra=extra)
                self._send(200, json.dumps({"ok": False, "error": str(e), "event_id": event_id, "http_status": 500}, ensure_ascii=False))
            return
        if parsed.path == "/api/no-exception-error":
            request_id = str(uuid.uuid4())
            event_id = str(uuid.uuid4())
            extra = {"event_id": event_id, "request_id": request_id}
            self.logger.error("api.error_without_exception", extra=extra)
            self._send(200, json.dumps({"ok": True, "event_id": event_id}, ensure_ascii=False))
            return
        if parsed.path == "/trigger":
            qs = parse_qs(parsed.query or "")
            mode = (qs.get("mode") or [self.default_mode])[0]
            request_id = (qs.get("request_id") or [str(uuid.uuid4())])[0]
            try:
                event_id = do_work(self.logger, mode=mode, request_id=request_id)
                self._send(200, json.dumps({"ok": True, "mode": mode, "event_id": event_id}, ensure_ascii=False))
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "mode": mode, "error": str(e), "http_status": 500}, ensure_ascii=False))
            return
        self._send(404, json.dumps({"error": "not_found"}, ensure_ascii=False))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/ingest":
            request_id = str(uuid.uuid4())
            event_id = str(uuid.uuid4())
            extra = {"event_id": event_id, "request_id": request_id}
            self.logger.info("api.ingest.start", extra=extra)
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                payload = json.loads(raw.decode("utf-8"))
                result = ingest_user(payload)
                self.logger.info("api.ingest.ok", extra=extra)
                self._send(200, json.dumps({"ok": True, "result": result, "event_id": event_id}, ensure_ascii=False))
            except Exception as e:
                self.logger.error("api.ingest.failed", exc_info=True, extra=extra)
                self._send(200, json.dumps({"ok": False, "error": str(e), "event_id": event_id, "http_status": 500}, ensure_ascii=False))
            return
        self._send(404, json.dumps({"error": "not_found"}, ensure_ascii=False))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.getenv("APP_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.getenv("APP_PORT", "9000")))
    p.add_argument("--log-path", default=os.getenv("LOG_PATH"))
    p.add_argument("--service-name", default=os.getenv("SERVICE_NAME", "demo-app"))
    p.add_argument("--environment", default=os.getenv("ENVIRONMENT", "dev"))
    p.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    p.add_argument(
        "--default-mode",
        default=os.getenv("DEFAULT_MODE", "value_error"),
        choices=["ok", "value_error", "zero_div", "no_exception_error", "java_like", "spam_info"],
    )
    p.add_argument("--tick-seconds", type=float, default=float(os.getenv("TICK_SECONDS", "5")))
    p.add_argument(
        "--tick-mode",
        default=os.getenv("TICK_MODE", "ok"),
        choices=["ok", "value_error", "zero_div", "no_exception_error", "java_like", "spam_info"],
    )
    return p.parse_args()


def main():
    args = parse_args()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = args.log_path or os.path.join(base_dir, "app.ndjson")
    logger = build_logger(log_path=log_path, service_name=args.service_name, environment=args.environment, level=args.log_level)

    DemoHandler.logger = logger
    DemoHandler.default_mode = args.default_mode
    httpd = ThreadingHTTPServer((args.host, int(args.port)), DemoHandler)

    logger.info(
        "service.started",
        extra={"event_id": str(uuid.uuid4()), "request_id": ""},
    )

    def ticker():
        while True:
            time.sleep(max(args.tick_seconds, 0.2))
            rid = str(uuid.uuid4())
            try:
                do_work(logger, mode=args.tick_mode, request_id=rid)
            except Exception:
                pass

    t = threading.Thread(target=ticker, daemon=True)
    t.start()

    print(f"demo service running: http://{args.host}:{args.port}")
    print(f"log_path: {log_path}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()