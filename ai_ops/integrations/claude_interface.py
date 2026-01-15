import re
import shlex
import subprocess

from ai_ops import config


class ClaudeInterface:
    def __init__(self):
        base = shlex.split(config.CLAUDE_COMMAND or "claude")
        extra = shlex.split(config.CLAUDE_ARGS or "")
        self.cmd = base + extra

    def execute_agentic_fix(self, error_content, cwd=None):
        prompt = (
            f"项目中出现了以下运行时错误，请在当前工作目录中定位相关代码并直接进行修复：\n\n"
            f"{error_content}\n\n"
            "修复完成后，请确保代码逻辑正确且不再报错。"
        )

        print(f"正在执行代理式修复 (Command: {' '.join(self.cmd)})...")
        result = subprocess.run(
            self.cmd + [prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            cwd=cwd,
        )
        return result.stdout

    def propose_fix_code_blocks(self, error_content):
        prompt = (
            "你是一个资深 Python 工程师。请根据下面的错误日志，在当前项目中给出修复方案。\n"
            "要求：\n"
            "1) 只输出一个或多个 <code_block filename=\"...\">...</code_block>，不要输出任何其它文字。\n"
            "2) 每个 code_block 的内容必须是对应文件的完整内容（不是 diff，也不是片段）。\n"
            "3) filename 必须是相对仓库根目录的路径，只能指向仓库内已存在的文件。\n"
            "   - 不要包含 workspaces/、repo/、磁盘盘符等运行环境路径前缀。\n"
            "   - 如果不确定目录结构，请优先只写文件名（例如 app.py）。\n"
            "4) 修复应尽量最小化改动，并保证代码可运行。\n\n"
            f"错误日志如下：\n{error_content}\n"
        )

        result = subprocess.run(
            self.cmd + [prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
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
        prompt = (
            f"用户遇到了以下错误：\n\n{error_content}\n\n"
            "代码已经尝试修复。请针对这次修复生成一份正式的报告，包含以下章节：\n"
            "1. **问题原因**：分析根本原因。\n"
            "2. **处理过程**：描述修复逻辑和采取的步骤。\n"
            "3. **最终结论**：总结修复效果及预防措施。\n"
            "请直接输出这三个章节的内容，不要包含其他闲聊。"
        )

        result = subprocess.run(
            self.cmd + [prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout
