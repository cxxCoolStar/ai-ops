import os
import subprocess
import config

class ClaudeInterface:
    def __init__(self):
        self.claude_cmd = config.CLAUDE_COMMAND

    def execute_agentic_fix(self, error_content):
        """
        调用 Claude Code 直接在当前项目中定位并修复错误。
        """
        prompt = (
            f"项目中出现了以下运行时错误，请在当前工作目录中定位相关代码并直接进行修复：\n\n"
            f"{error_content}\n\n"
            "修复完成后，请确保代码逻辑正确且不再报错。"
        )
        
        # 使用 -y 开启自动运行模式（如果支持），或者直接传递指令
        # 假设 claude CLI 支持接收 prompt 并自动处理
        try:
            print(f"正在执行代理式修复 (Command: {self.claude_cmd})...")
            # 注意：某些版本的 claude CLI 可能需要特定的非交互模式参数，如 '-y'
            # 这里先按用户指令集成的逻辑：直接调用
            result = subprocess.run(
                [self.claude_cmd, prompt],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            return result.stdout
        except Exception as e:
            return f"代理修复执行异常: {e}"

    def get_structured_summary(self, error_content):
        """
        在修复完成后，调用 Claude 生成一份结构化的 PR 报告。
        """
        prompt = (
            f"用户遇到了以下错误：\n\n{error_content}\n\n"
            "代码已经尝试修复。请针对这次修复生成一份正式的报告，包含以下章节：\n"
            "1. **问题原因**：分析根本原因。\n"
            "2. **处理过程**：描述修复逻辑和采取的步骤。\n"
            "3. **最终结论**：总结修复效果及预防措施。\n"
            "请直接输出这三个章节的内容，不要包含其他闲聊。"
        )
        
        try:
            result = subprocess.run(
                [self.claude_cmd, prompt],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            return result.stdout
        except Exception as e:
            return f"获取分析摘要失败: {e}"

if __name__ == "__main__":
    # 模拟测试
    # ci = ClaudeInterface()
    # print(ci.get_structured_summary("ValueError: invalid literal for int()"))
    pass
