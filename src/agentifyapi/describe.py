"""Agent-friendly tool descriptions. Pluggable: OpenAI / Anthropic via env, template fallback."""

from __future__ import annotations

import json
import os

import httpx


def template_description(tool: dict) -> str:
    verb = {"GET": "Read", "POST": "Create", "PUT": "Replace", "PATCH": "Update", "DELETE": "Delete"}.get(
        tool["method"], tool["method"]
    )
    head = tool.get("summary") or f"{verb} via {tool['method']} {tool['path']}"
    parts = [head.rstrip(".") + "."]
    if tool.get("doc") and tool["doc"] != tool.get("summary"):
        parts.append(tool["doc"].strip())
    props = tool["input_schema"].get("properties", {})
    req = set(tool["input_schema"].get("required", []))
    if props:
        args = ", ".join(f"{k}{'' if k in req else '?'}" for k in props)
        parts.append(f"Arguments: {args}.")
    if tool["method"] in ("POST", "PUT", "PATCH", "DELETE"):
        parts.append("This tool has side effects.")
    if tool.get("tags"):
        parts.append(f"Tags: {', '.join(tool['tags'])}.")
    return " ".join(parts)


PROMPT = (
    "Write a 1-3 sentence description of this API operation for an AI agent choosing tools. "
    "Say what it does, when to use it, key arguments, and whether it has side effects. "
    "Plain text only.\n\n"
)


def llm_description(tool: dict) -> str | None:
    payload = json.dumps({k: tool[k] for k in ("name", "method", "path", "summary", "doc", "input_schema")})[:6000]
    try:
        if os.getenv("ANTHROPIC_API_KEY"):
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                timeout=30,
                headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                json={
                    "model": os.getenv("AGENTIFYAPI_LLM_MODEL", "claude-3-5-haiku-latest"),
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": PROMPT + payload}],
                },
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"].strip()
        if os.getenv("OPENAI_API_KEY"):
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                timeout=30,
                headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                json={
                    "model": os.getenv("AGENTIFYAPI_LLM_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": PROMPT + payload}],
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
    return None


def describe(tool: dict) -> str:
    if os.getenv("AGENTIFYAPI_DESCRIBER", "auto") != "template":
        text = llm_description(tool)
        if text:
            return text
    return template_description(tool)
