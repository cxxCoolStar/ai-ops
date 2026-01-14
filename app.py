```python
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
    """
    处理数据并转换为整数
    
    Args:
        data: 输入数据，可以是字符串或数字
        
    Returns:
        int: 转换后的整数值，如果转换失败返回 None
    """
    logging.debug(f"正在处理数据: {data}")
    
    try:
        # 尝试转换为整数
        result = int(data)
        logging.info(f"数据转换成功: {data} -> {result}")
        return result
        
    except (ValueError, TypeError) as e:
        # 处理转换失败的情况
        logging.error(f"数据转换失败: '{data}' 无法转换为整数 - {type(e).__name__}: {e}")
        return None

def main():
    logging.info("服务已启动 - v1.0.0")
    print("服务已启动，正在运行...")
    
    # 模拟一些正常操作
    time.sleep(1)
    logging.info("初始化组件成功")
    
    # 模拟业务逻辑
    items = ["100", "200", "abc", "300"]
    success_count = 0
    failure_count = 0
    
    for item in items:
        logging.info(f"开始处理项目: {item}")
        time.sleep(0.5)
        
        result = process_data(item)
        
        if result is not None:
            logging.info(f"项目处理成功: {result}")
            success_count += 1
        else:
            logging.warning(f"项目处理失败: {item} (无效输入)")
            failure_count += 1
    
    # 输出统计信息
    logging.info(f"处理完成 - 成功: {success_count}, 失败: {failure_count}")
    print(f"\n处理完成 - 成功: {success_count}, 失败: {failure_count}")
    print(f"成功率: {success_count / len(items) * 100:.1f}%")

if __name__ == "__main__":
    main()
```