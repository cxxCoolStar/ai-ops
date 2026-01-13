import subprocess
import config

class ClaudeInterface:
    def __init__(self):
        self.command = config.CLAUDE_COMMAND

    def analyze_error(self, error_content):
        prompt = (
            f"你是一个智能技术专家。用户遇到了以下错误：\n\n{error_content}\n\n"
            "请执行以下操作：\n"
            "1. **阅读代码**：根据错误信息中的文件路径或上下文，读取相关源代码文件。\n"
            "2. **分析诊断**：分析错误原因。\n"
            "3. **给出方案**：不要提供多个选项！请直接执行你认为**最完善、最推荐**的一个解决方案。\n"
            "4. **代码修复**：提供修改后的完整代码片段或Diff。\n"
            "5. **解释原因**：简要说明为什么这个方案是最好的。\n"
        )
        
        try:
            # 修复：Windows 下使用 shell=True 且传递列表参数时，后续参数会被 Shell 吞掉而不是传给命令
            # 改为 shell=False，Python 会自动处理参数转义
            result = subprocess.run(
                [self.command, prompt],
                capture_output=True,
                text=True,
                encoding='utf-8',
                shell=False 
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Claude 分析失败 (错误代码 {result.returncode}): {result.stderr}"
        except Exception as e:
            return f"调用 Claude 时发生异常: {e}"

if __name__ == "__main__":
    # 简单测试
    claude = ClaudeInterface()
    # print(claude.analyze_error("ZeroDivisionError: division by zero"))
