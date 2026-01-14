import subprocess
import re
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
        print(f"正在执行代理式修复 (Command: {self.claude_cmd})...")
        result = subprocess.run(
            [self.claude_cmd, prompt],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        return result.stdout

    def propose_fix_code_blocks(self, error_content):
        prompt = (
            "你是一个资深 Python 工程师。请根据下面的错误日志，在当前项目中给出修复方案。\n"
            "要求：\n"
            "1) 只输出一个或多个 <code_block filename=\"...\">...</code_block>，不要输出任何其它文字。\n"
            "2) 每个 code_block 的内容必须是对应文件的完整内容（不是 diff，也不是片段）。\n"
            "3) filename 使用相对路径，只能指向当前项目内已存在的文件。\n"
            "4) 修复应尽量最小化改动，并保证代码可运行。\n\n"
            f"错误日志如下：\n{error_content}\n"
        )

        result = subprocess.run(
            [self.claude_cmd, prompt],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        blocks = self._parse_code_blocks(result.stdout)
        if not blocks:
            raise ValueError("Claude 未返回任何 code_block。")
        return blocks

    def _parse_code_blocks(self, text):
        pattern = r'<code_block\s+filename="([^"]+)">\s*([\s\S]*?)\s*</code_block>'
        matches = re.findall(pattern, text or "", flags=re.IGNORECASE)
        return [(filename.strip(), content) for filename, content in matches if filename.strip()]

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
        
        result = subprocess.run(
            [self.claude_cmd, prompt],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        return result.stdout

if __name__ == "__main__":
    # 模拟测试
    # ci = ClaudeInterface()
    # print(ci.get_structured_summary("ValueError: invalid literal for int()"))
    pass
