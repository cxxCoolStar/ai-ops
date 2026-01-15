#!/usr/bin/env python3
"""
演示应用：用于测试 AI 运维代理的自动修复功能

这个应用故意包含一些 Bug，用于展示：
1. 自动错误检测和上报
2. Claude 分析问题并生成修复方案
3. 自动应用修复并验证
"""

import logging
import sqlite3
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import threading
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S.%fZ'
)
logger = logging.getLogger('demo-app')


class DatabaseError(Exception):
    """自定义数据库错误"""
    pass


def parse_int(value):
    """
    解析整数值
    
    Bug: 没有处理 None 和空字符串的情况
    """
    return int(value.strip() if isinstance(value, str) else value)


def validate_positive(num):
    """
    验证数字是否为正数
    
    Bug: 没有处理 0 的情况
    """
    if num < 0:
        raise ValueError(f"Expected positive number, got {num}")
    return num


def divide(a, b):
    """
    除法运算
    
    Bug: 没有检查除数是否为 0
    """
    return parse_int(a) / parse_int(b)


def calculate_statistics(numbers):
    """
    计算统计数据
    
    Bug: 没有验证输入是否为空列表
    """
    total = sum(numbers)
    average = total / len(numbers)
    return {
        'total': total,
        'average': average,
        'count': len(numbers)
    }


def query_user(user_id):
    """
    查询用户信息
    
    Bug: SQL 注入风险，没有使用参数化查询
    """
    conn = sqlite3.connect('data/app.db')
    cursor = conn.cursor()
    
    # 危险：直接拼接 SQL
    sql = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(sql)
    
    result = cursor.fetchone()
    conn.close()
    
    return result


def save_trace(trace_data):
    """
    保存追踪数据
    
    Bug: 没有处理数据库连接失败的情况
    """
    conn = sqlite3.connect('data/traces.db')
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO traces (timestamp, event_type, data) VALUES (?, ?, ?)",
        (trace_data['timestamp'], trace_data['event_type'], json.dumps(trace_data))
    )
    
    conn.commit()
    conn.close()


class DemoAPIHandler(BaseHTTPRequestHandler):
    """演示 API 处理器"""
    
    def _set_headers(self, status_code=200, content_type='application/json'):
        """设置响应头"""
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
    
    def _send_json_response(self, data, status_code=200):
        """发送 JSON 响应"""
        self._set_headers(status_code)
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def _send_error(self, message, status_code=500):
        """发送错误响应"""
        self._send_json_response({'error': message}, status_code)
    
    def do_GET(self):
        """处理 GET 请求"""
        try:
            # 解析 URL 和查询参数
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)
            
            logger.info(f"Received GET request: {parsed_path.path}")
            
            # 路由处理
            if parsed_path.path == '/api/divide':
                # 除法 API
                a = query_params.get('a', ['10'])[0]
                b = query_params.get('b', ['0'])[0]
                
                try:
                    result = divide(a, b)
                    self._send_json_response({
                        'operation': 'divide',
                        'operands': [a, b],
                        'result': result
                    })
                except (ValueError, ZeroDivisionError) as e:
                    logger.error(f"Divide error: {e}")
                    self._send_error(str(e), 400)
            
            elif parsed_path.path == '/api/statistics':
                # 统计 API
                numbers_param = query_params.get('numbers', [''])[0]
                
                if not numbers_param:
                    self._send_error('Missing numbers parameter', 400)
                    return
                
                try:
                    numbers = [int(n.strip()) for n in numbers_param.split(',')]
                    result = calculate_statistics(numbers)
                    self._send_json_response(result)
                except (ValueError, ZeroDivisionError) as e:
                    logger.error(f"Statistics error: {e}")
                    self._send_error(str(e), 400)
            
            elif parsed_path.path == '/api/user':
                # 用户查询 API
                user_id = query_params.get('id', ['1'])[0]
                
                try:
                    user = query_user(user_id)
                    if user:
                        self._send_json_response({
                            'id': user[0],
                            'name': user[1],
                            'email': user[2]
                        })
                    else:
                        self._send_error('User not found', 404)
                except Exception as e:
                    logger.error(f"User query error: {e}")
                    self._send_error(str(e), 500)
            
            elif parsed_path.path == '/api/health':
                # 健康检查
                self._send_json_response({
                    'status': 'healthy',
                    'timestamp': time.time()
                })
            
            elif parsed_path.path == '/api/trigger-error':
                # 触发错误用于演示
                error_type = query_params.get('type', ['division'])[0]
                
                if error_type == 'division':
                    # 触发除零错误
                    self._send_error('Triggering division by zero error', 500)
                    result = divide(10, 0)
                
                elif error_type == 'sql':
                    # 触发 SQL 错误
                    self._send_error('Triggering SQL injection', 500)
                    result = query_user("1; DROP TABLE users; --")
                
                elif error_type == 'empty_stats':
                    # 触发空列表统计错误
                    self._send_error('Triggering empty statistics error', 500)
                    result = calculate_statistics([])
                
                else:
                    self._send_error('Unknown error type', 400)
            
            else:
                self._send_error('Not found', 404)
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            self._send_error(str(e), 500)
    
    def do_POST(self):
        """处理 POST 请求"""
        try:
            parsed_path = urlparse(self.path)
            
            logger.info(f"Received POST request: {parsed_path.path}")
            
            if parsed_path.path == '/api/trace':
                # 接收追踪数据
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                
                try:
                    trace_data = json.loads(post_data.decode('utf-8'))
                    save_trace(trace_data)
                    self._send_json_response({'status': 'success'})
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    self._send_error('Invalid JSON', 400)
                except Exception as e:
                    logger.error(f"Save trace error: {e}")
                    self._send_error(str(e), 500)
            
            else:
                self._send_error('Not found', 404)
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            self._send_error(str(e), 500)
    
    def log_message(self, format, *args):
        """覆盖默认的日志方法"""
        logger.info(f"{self.address_string()} - {format % args}")


def init_database():
    """初始化数据库"""
    os.makedirs('data', exist_ok=True)
    
    # 创建应用数据库
    conn = sqlite3.connect('data/app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL
        )
    ''')
    
    # 插入测试数据
    cursor.execute("INSERT OR IGNORE INTO users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')")
    cursor.execute("INSERT OR IGNORE INTO users (id, name, email) VALUES (2, 'Bob', 'bob@example.com')")
    cursor.execute("INSERT OR IGNORE INTO users (id, name, email) VALUES (3, 'Charlie', 'charlie@example.com')")
    
    conn.commit()
    conn.close()
    
    # 创建追踪数据库
    conn = sqlite3.connect('data/traces.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info("Database initialized successfully")


def run_server(port=8888):
    """启动 HTTP 服务器"""
    init_database()
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, DemoAPIHandler)
    
    logger.info(f"Demo server starting on port {port}")
    logger.info(f"Available endpoints:")
    logger.info(f"  GET  /api/health")
    logger.info(f"  GET  /api/divide?a=10&b=2")
    logger.info(f"  GET  /api/statistics?numbers=1,2,3,4,5")
    logger.info(f"  GET  /api/user?id=1")
    logger.info(f"  GET  /api/trigger-error?type=division")
    logger.info(f"  POST /api/trace")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
        httpd.shutdown()


if __name__ == '__main__':
    run_server()