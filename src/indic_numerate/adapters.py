"""Thin model adapters. One method, one contract.

An adapter turns a prompt into text. It knows nothing about scoring, caching or
document handling; the runner owns those. Adding a model means ~15 lines here
and nothing anywhere else.

Three ship: two API models (Anthropic, OpenAI) and one local (Ollama). Their
SDKs are optional dependencies and are imported inside `generate`, so the
deterministic test suite and CI never need them installed.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol


class Adapter(Protocol):
    name: str
    version: str  # pinned model version; part of the cache key

    def generate(self, prompt: str) -> str: ...


class AnthropicAdapter:
    def __init__(self, model: str = "claude-sonnet-5", max_tokens: int = 2000):
        self.name = f"anthropic/{model}"
        self.version = model
        self.max_tokens = max_tokens

    def generate(self, prompt: str) -> str:
        import anthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set; the harness will not call an API blind")
        resp = anthropic.Anthropic().messages.create(
            model=self.version,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


class OpenAIAdapter:
    def __init__(self, model: str = "gpt-4.1", max_tokens: int = 2000):
        self.name = f"openai/{model}"
        self.version = model
        self.max_tokens = max_tokens

    def generate(self, prompt: str) -> str:
        import openai

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set; the harness will not call an API blind")
        resp = openai.OpenAI().chat.completions.create(
            model=self.version,
            max_completion_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""


class OllamaAdapter:
    """Local models. Uses urllib so no SDK is required at all."""

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434",
                 timeout: int = 900):
        self.name = f"ollama/{model}"
        self.version = model
        self.host = host.rstrip("/")
        # A document-context prompt is tens of thousands of tokens; a local model
        # on CPU can take many minutes on one item. The old fixed 300s ceiling
        # timed out mid-run and looked like an unreachable server.
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        body = json.dumps({"model": self.version, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self.host}/api/generate", data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())["response"]
        except OSError as exc:
            raise RuntimeError(
                f"could not reach Ollama at {self.host}: {exc}. Start it with `ollama serve` "
                f"and pull the model with `ollama pull {self.version}`."
            ) from exc


class EchoAdapter:
    """Returns a canned response. For testing the runner without a model.

    NOT a baseline and never reported as one: it does not read documents and
    exists only so the harness has a deterministic adapter in CI.
    """

    def __init__(self, response: str = "{}", name: str = "echo"):
        self.name = name
        self.version = "echo-1"
        self.response = response

    def generate(self, prompt: str) -> str:
        return self.response


BUILTIN = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "ollama": OllamaAdapter,
    "echo": EchoAdapter,
}


def build(spec: str) -> Adapter:
    """'anthropic:claude-sonnet-5' -> AnthropicAdapter('claude-sonnet-5')."""
    provider, _, model = spec.partition(":")
    if provider not in BUILTIN:
        raise ValueError(f"unknown adapter {provider!r}; expected one of {sorted(BUILTIN)}")
    return BUILTIN[provider](model) if model else BUILTIN[provider]()
