"""
ForgeAgent — code generation specialist with agentic loop.

Flow:
  1. Claude receives the task + FORGE_TOOLS (read_file, write_file, run_linter)
  2. Claude generates code and calls tools as needed
  3. ForgeAgent executes each tool call and feeds results back to Claude
  4. Loop continues until end_turn or MAX_ITERATIONS hit
  5. Returns the final AgentOutput

File I/O is NOT sandboxed by default — callers pass explicit paths.
The linter (ruff) runs in a subprocess with a 30s timeout.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

from agents.base_agent import AgentInput, AgentOutput, BaseAgent
from services.db import get_db_service

logger = logging.getLogger("cruz.agents.FORGE")

_MODEL = "claude-sonnet-4-6"
_MAX_ITERATIONS = 10

_SYSTEM_PROMPT = """You are FORGE, an expert software engineer embedded in the CRUZ AI system.

You have access to tools to read files, write files, and run a linter.

Guidelines:
- Read existing files before modifying them to preserve context
- Write clean, typed, production-ready code
- Run the linter after writing code and fix any issues it reports
- Use markdown code blocks in explanations, but write raw code to files via write_file
- When you are done, respond with a brief summary of what you built"""

# ─────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────

FORGE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file at the given path. "
            "Use this to inspect existing code before modifying it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file, creating it (and any parent directories) "
            "if it doesn't exist. Overwrites existing content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path where the file should be written.",
                },
                "content": {
                    "type": "string",
                    "description": "The file content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_linter",
        "description": (
            "Run a linter on a file. Uses ruff for Python (.py), "
            "and reports syntax errors for JS/TS files. "
            "Returns 'passed' if no issues, or the error output if issues found. "
            "Always lint files after writing them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to lint (.py, .js, .ts, .tsx).",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": (
            "List the contents of a directory. "
            "Shows files and subdirectories at the given path. "
            "Use this to explore project structure before reading or writing files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory to list.",
                }
            },
            "required": ["path"],
        },
    },
]


# ─────────────────────────────────────────────
# Tool executors
# ─────────────────────────────────────────────

def _execute_read_file(path: str) -> str:
    try:
        content = Path(path).read_text(encoding="utf-8")
        return content
    except FileNotFoundError:
        return f"error: file not found at '{path}'"
    except PermissionError:
        return f"error: permission denied reading '{path}'"
    except Exception as exc:
        return f"error: {exc}"


def _execute_write_file(path: str, content: str) -> str:
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"written: '{path}' ({len(content)} chars)"
    except PermissionError:
        return f"error: permission denied writing '{path}'"
    except Exception as exc:
        return f"error: {exc}"


async def _execute_run_linter(path: str) -> str:
    if not Path(path).exists():
        return f"error: file not found at '{path}'"

    ext = Path(path).suffix.lower()

    # JS / TS files
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        return await _execute_run_linter_js(path)

    # Python files (default)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ruff", "check", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

        if proc.returncode == 0:
            return "passed: ruff found no issues"

        output = stdout.decode("utf-8").strip() or stderr.decode("utf-8").strip()
        return f"failed:\n{output}"

    except FileNotFoundError:
        # ruff not installed — try py_compile as fallback
        return await _lint_with_py_compile(path)
    except asyncio.TimeoutError:
        return "error: linter timed out after 30 seconds"
    except Exception as exc:
        return f"error running linter: {exc}"


async def _lint_with_py_compile(path: str) -> str:
    """Fallback: use Python's built-in compile() to catch syntax errors."""
    try:
        source = Path(path).read_text(encoding="utf-8")
        compile(source, path, "exec")
        return "passed: no syntax errors found (ruff not available)"
    except SyntaxError as e:
        return f"failed: syntax error on line {e.lineno}: {e.msg}"
    except Exception as exc:
        return f"error: {exc}"


async def _execute_run_linter_js(path: str) -> str:
    """Run eslint on a JS/TS file, falling back to a basic parse check."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "npx", "eslint", "--no-eslintrc", "-c", "{}", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        if proc.returncode == 0:
            return "passed: eslint found no issues"
        output = stdout.decode("utf-8").strip() or stderr.decode("utf-8").strip()
        return f"failed:\n{output}"
    except (FileNotFoundError, asyncio.TimeoutError):
        # eslint not available — do a basic check via node
        return await _lint_js_with_node(path)
    except Exception as exc:
        return f"error running eslint: {exc}"


async def _lint_js_with_node(path: str) -> str:
    """Fallback: use node --check for basic JS/TS syntax validation."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "node", "--check", path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        if proc.returncode == 0:
            return "passed: no syntax errors found (node --check)"
        output = stderr.decode("utf-8").strip() or stdout.decode("utf-8").strip()
        return f"failed:\n{output}"
    except FileNotFoundError:
        return "passed: linter not available for this file type (install eslint or node)"
    except asyncio.TimeoutError:
        return "error: linter timed out"
    except Exception as exc:
        return f"error: {exc}"


def _execute_list_directory(path: str) -> str:
    """List files and subdirectories at the given path."""
    target = Path(path)
    if not target.exists():
        return f"error: directory not found at '{path}'"
    if not target.is_dir():
        return f"error: '{path}' is a file, not a directory"
    try:
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            prefix = "📄 " if entry.is_file() else "📁 "
            lines.append(f"{prefix}{entry.name}")
        return "\n".join(lines) if lines else "(empty directory)"
    except PermissionError:
        return f"error: permission denied reading '{path}'"
    except Exception as exc:
        return f"error: {exc}"


# ─────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────

class ForgeAgent(BaseAgent):
    """
    Code generation agent with an internal agentic loop.

    Calls Claude with FORGE_TOOLS, executes tool calls (read_file,
    write_file, run_linter), and continues until Claude signals end_turn
    or MAX_ITERATIONS is reached.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "FORGE"

    async def process(self, input: AgentInput) -> AgentOutput:
        start = time.monotonic()
        total_tokens = 0

        try:
            client = anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )

            messages: List[Dict[str, Any]] = [
                {"role": "user", "content": input["task"]}
            ]

            for iteration in range(_MAX_ITERATIONS):
                response = await client.messages.create(
                    model=_MODEL,
                    max_tokens=8096,
                    system=_SYSTEM_PROMPT,
                    tools=FORGE_TOOLS,
                    messages=messages,
                )

                total_tokens += response.usage.input_tokens + response.usage.output_tokens

                # ── End of loop ──────────────────────────────────────────
                if response.stop_reason == "end_turn":
                    text = _extract_text(response.content)
                    duration = int((time.monotonic() - start) * 1000)
                    await self.log(
                        db=get_db_service(),
                        trace_id=input["trace_id"],
                        status="success",
                        input_data={"task": input["task"]},
                        output_data={"result": text},
                        tokens_used=total_tokens,
                        duration_ms=duration,
                    )
                    return AgentOutput(
                        success=True,
                        result=text,
                        agent=self.name,
                        duration_ms=duration,
                        tokens_used=total_tokens,
                        error=None,
                        requires_approval=False,
                        approval_prompt=None,
                    )

                # ── Tool use ─────────────────────────────────────────────
                if response.stop_reason == "tool_use":
                    tool_results: List[Dict[str, Any]] = []

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        tool_result = await self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result,
                        })

                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # ── Unexpected stop_reason ───────────────────────────────
                text = _extract_text(response.content)
                return AgentOutput(
                    success=True,
                    result=text or "",
                    agent=self.name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    tokens_used=total_tokens,
                    error=None,
                    requires_approval=False,
                    approval_prompt=None,
                )

            # ── Max iterations hit ────────────────────────────────────────
            logger.warning(
                "[%s] FORGE hit max iterations (%d) — returning partial result",
                input["trace_id"],
                _MAX_ITERATIONS,
            )
            return AgentOutput(
                success=False,
                result=None,
                agent=self.name,
                duration_ms=int((time.monotonic() - start) * 1000),
                tokens_used=total_tokens,
                error=f"Exceeded maximum loop iterations ({_MAX_ITERATIONS}). Task may be too complex.",
                requires_approval=False,
                approval_prompt=None,
            )

        except Exception as exc:
            output = self.handle_error(exc, input["trace_id"])
            try:
                await self.log(
                    db=get_db_service(),
                    trace_id=input["trace_id"],
                    status="error",
                    input_data={"task": input["task"]},
                    output_data={"error": str(exc)},
                    tokens_used=0,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return output

    async def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Dispatch a tool call and return the result as a string."""
        if tool_name == "read_file":
            return _execute_read_file(tool_input.get("path", ""))

        if tool_name == "write_file":
            return _execute_write_file(
                tool_input.get("path", ""),
                tool_input.get("content", ""),
            )

        if tool_name == "run_linter":
            return await _execute_run_linter(tool_input.get("path", ""))

        if tool_name == "list_directory":
            return _execute_list_directory(tool_input.get("path", ""))

        return f"error: unknown tool '{tool_name}'"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _extract_text(content: List[Any]) -> str:
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            return block.text
    return ""
