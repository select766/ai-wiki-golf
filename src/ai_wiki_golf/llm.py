from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List

from openai import OpenAI
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from .config import LLMConfig


@dataclass
class LLMResult:
    text: str
    usage: dict[str, Any]


class BaseLLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def generate(self, messages: List[dict[str, str]], **kwargs: Any) -> LLMResult:
        raise NotImplementedError


class OpenRouterClient(BaseLLMClient):
    def __init__(self, config: LLMConfig, api_key: str):
        super().__init__(config)
        base_url = config.base_url or "https://openrouter.ai/api/v1"
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, messages: List[dict[str, str]], **kwargs: Any) -> LLMResult:
        request_options = {k: v for k, v in (self.config.options or {}).items()}
        if "max_output_tokens" in request_options and "max_tokens" not in request_options:
            request_options["max_tokens"] = request_options.pop("max_output_tokens")
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            timeout=self.config.timeout,
            **request_options,
            **kwargs,
        )
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = {
            "input_tokens": getattr(response.usage, "prompt_tokens", None),
            "output_tokens": getattr(response.usage, "completion_tokens", None),
        }
        return LLMResult(text=text.strip(), usage=usage)


class GeminiClient(BaseLLMClient):
    def __init__(self, config: LLMConfig, api_key: str):
        super().__init__(config)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            config.model,
            generation_config=config.options or None,
        )
        self.max_retries = 6

    def generate(self, messages: List[dict[str, str]], **kwargs: Any) -> LLMResult:
        contents = []
        role_map = {"system": "user", "assistant": "model"}
        for msg in messages:
            role = role_map.get(msg["role"], msg["role"])
            contents.append({"role": role, "parts": [msg["content"]]})
        last_error: Exception | None = None
        response = None
        for attempt in range(self.max_retries):
            try:
                response = self.model.generate_content(contents)
                last_error = None
                break
            except google_exceptions.ResourceExhausted as exc:
                last_error = exc
                delay = getattr(exc, "retry_delay", None)
                sleep_seconds = 10 * (attempt + 1)
                if delay is not None:
                    sleep_seconds = max(
                        sleep_seconds,
                        getattr(delay, "seconds", 0) + getattr(delay, "nanos", 0) / 1_000_000_000,
                    )
                time.sleep(sleep_seconds)
            except google_exceptions.GoogleAPICallError as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
        if response is None:
            raise last_error or RuntimeError("Gemini generate_content failed")
        text = response.text or ""
        usage = {
            "input_tokens": getattr(response.usage_metadata, "prompt_token_count", None),
            "output_tokens": getattr(response.usage_metadata, "candidates_token_count", None),
        }
        return LLMResult(text=text.strip(), usage=usage)


def build_llm_client(config: LLMConfig, env: dict[str, str]) -> BaseLLMClient:
    if config.provider == "openrouter":
        api_key = env.get("OPENROUTER_API_KEY") or env.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY or OPENAI_API_KEY is required for OpenRouter provider")
        return OpenRouterClient(config, api_key)
    if config.provider == "gemini":
        api_key = env.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini provider")
        return GeminiClient(config, api_key)
    raise ValueError(f"Unknown LLM provider: {config.provider}")
