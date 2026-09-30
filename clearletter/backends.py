"""Two ways to reach Claude. The pipeline works the same with either.

- ApiBackend: the Anthropic API (Python SDK). Needs an API key; billed per token.
  This is the reference implementation.
- ClaudeCodeBackend: runs each step through the Claude Code command line
  (`claude -p`) using the developer's own Claude subscription. No API key and
  no per-token bill; calls count against the subscription's usage limits.

Each backend offers the same two operations:
    structured(system, user_text, schema) -> (parsed answer, [call record])
    write_with_tools(system, user_text)   -> (text, [call records])
A call record is a dict: input_tokens, output_tokens, cost_usd, refused.
"""

import json
import os
import subprocess
import sys

from .config import MAX_TOKENS
from .tools import glossary_lookup, readability_check


class ApiBackend:
    name = "api"

    def __init__(self, cfg, client=None):
        import anthropic
        self.cfg = cfg
        self.client = client or anthropic.Anthropic()

    def _call_record(self, message):
        usage = message.usage
        return {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": self.cfg.cost(usage.input_tokens, usage.output_tokens),
            "refused": message.stop_reason == "refusal",
        }

    def structured(self, system, user_text, schema):
        message = self.client.messages.parse(
            model=self.cfg.model_id,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_format=schema,
            **self.cfg.extra,
        )
        return message.parsed_output, [self._call_record(message)]

    def write_with_tools(self, system, user_text):
        # The tool runner lets Claude call our tools as many times as it needs,
        # then returns its final answer. max_iterations stops endless loops.
        runner = self.client.beta.messages.tool_runner(
            model=self.cfg.model_id,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=[glossary_lookup, readability_check],
            messages=[{"role": "user", "content": user_text}],
            max_iterations=8,
            **self.cfg.extra,
        )
        calls, final = [], None
        for message in runner:
            calls.append(self._call_record(message))
            final = message
        text = "".join(block.text for block in final.content if block.type == "text").strip()
        return text, calls


class ClaudeCodeBackend:
    name = "claude-code"

    # Settings that keep each call clean and private: none of the developer's
    # own settings, plugins, hooks, MCP servers or CLAUDE.md files are loaded,
    # Claude Code's built-in tools (files, shell, web) are switched off, and
    # nothing is saved as a session.
    BASE = [
        "claude", "-p", "--output-format", "json",
        "--setting-sources", "", "--strict-mcp-config",
        "--disable-slash-commands", "--no-session-persistence",
        "--tools", "",
    ]
    MCP_CONFIG = json.dumps({"mcpServers": {"clearletter": {
        "command": sys.executable, "args": ["-m", "clearletter.mcp_tools"],
    }}})
    MCP_TOOLS = "mcp__clearletter__glossary_lookup,mcp__clearletter__readability_check"

    def __init__(self, cfg, runner=subprocess.run):
        self.cfg = cfg
        self.runner = runner  # replaceable in tests

    def _run(self, system, user_text, extra):
        command = self.BASE + ["--model", self.cfg.model_id, "--system-prompt", system] + extra
        effort = self.cfg.extra.get("output_config", {}).get("effort")
        if effort:
            command += ["--effort", effort]
        # Remove any API key from the environment, so these calls always use the
        # subscription and can never be billed to an API account by accident.
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        process = self.runner(command, input=user_text, capture_output=True, text=True,
                              timeout=900, env=env, cwd=project_root)
        try:
            data = json.loads(process.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Claude Code did not return JSON: {process.stdout[:300]} {process.stderr[:300]}")
        refused = data.get("stop_reason") == "refusal"
        if data.get("is_error") and not refused:
            raise RuntimeError(f"Claude Code error: {data.get('result') or data.get('subtype')}")
        usage = data.get("usage", {})
        record = {
            "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            # What the same tokens would cost on the API at list price, as reported
            # by Claude Code. Nothing is charged: the subscription covers it.
            "cost_usd": data.get("total_cost_usd", 0.0),
            "refused": refused,
            "turns": data.get("num_turns"),  # more than 1 means Claude used a tool
        }
        return data, record

    def structured(self, system, user_text, schema):
        data, record = self._run(system, user_text,
                                 ["--json-schema", json.dumps(schema.model_json_schema())])
        parsed = None if record["refused"] else schema.model_validate(data["structured_output"])
        return parsed, [record]

    def write_with_tools(self, system, user_text):
        data, record = self._run(system, user_text, [
            "--mcp-config", self.MCP_CONFIG,
            "--allowedTools", self.MCP_TOOLS,
            "--max-turns", "10",
        ])
        return (data.get("result") or "").strip(), [record]


def make_backend(name, cfg, client=None):
    if name == "api":
        return ApiBackend(cfg, client)
    if name == "claude-code":
        return ClaudeCodeBackend(cfg)
    raise ValueError(f"Unknown backend {name!r}")
