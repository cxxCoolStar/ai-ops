import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_ops.agent.agent import Agent
from ai_ops.config import Config
from ai_ops.trace.trace_store import TraceStore
from ai_ops.integrations.claude_interface import ClaudeInterface


async def do_work():
    """模拟可能失败的工作"""
    # 故意触发一个 ValueError
    try:
        int("abc")
    except ValueError as e:
        print(f"Caught expected error: {e}")
        # 可以选择重新抛出或处理
        # raise
    return "work completed successfully"


async def main():
    """主函数"""
    # 初始化配置
    config = Config()
    
    # 初始化追踪存储
    trace_store = TraceStore(config.trace_db_path)
    
    # 初始化 Claude 接口
    claude_interface = ClaudeInterface(
        api_key=config.claude_api_key,
        model=config.claude_model
    )
    
    # 创建 Agent
    agent = Agent(
        trace_store=trace_store,
        claude_interface=claude_interface
    )
    
    # 执行工作
    result = await do_work()
    print(f"Result: {result}")
    
    # 清理资源
    await trace_store.close()


if __name__ == "__main__":
    asyncio.run(main())