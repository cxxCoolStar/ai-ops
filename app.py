import logging
import time
import random

# 配置日志
logging.basicConfig(
    filename='app.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)

def process_data(data):
    logging.debug(f"正在处理数据: {data}")
    try:
        # 尝试将数据转换为整数
        return int(data)
    except ValueError as e:
        # 记录错误并返回 None，而不是抛出异常
        logging.warning(f"无法将数据 '{data}' 转换为整数: {e}")
        return None
    except TypeError as e:
        # 处理其他类型错误
        logging.warning(f"数据类型错误: {e}")
        return None

def main():
    logging.info("服务已启动 - v1.0.0")
    print("服务已启动，正在运行...")
    
    # 模拟一些正常操作
    time.sleep(1)
    logging.info("初始化组件成功")
    
    try:
        # 模拟业务逻辑
        items = ["100", "200", "abc", "300"]
        for item in items:
            logging.info(f"开始处理项目: {item}")
            time.sleep(0.5)
            result = process_data(item)
            
            # 只在成功时记录
            if result is not None:
                logging.info(f"项目处理成功: {result}")
            
    except Exception as e:
        # 使用 exc_info=True 记录完整的堆栈信息
        logging.error("处理过程中发生严重错误", exc_info=True)
        print(f"发生错误: {e}")

if __name__ == "__main__":
    main()
