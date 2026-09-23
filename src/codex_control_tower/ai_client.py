"""Shared OpenAI-compatible client for user-selected AI providers."""

from __future__ import annotations

import json
import os
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from .paths import ENV_FILE


LEGACY_DEEPSEEK_KEY_FILE = Path.home() / ".config/deepseek-tools/api-key"
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "api_url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-v4-flash",
        "key_name": "DEEPSEEK_API_KEY",
        "base_name": "DEEPSEEK_BASE_URL",
        "model_name": "DEEPSEEK_MODEL",
    },
    "qwen": {
        "label": "千问",
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model": "qwen3.6-flash",
        "key_name": "DASHSCOPE_API_KEY",
        "base_name": "QWEN_BASE_URL",
        "model_name": "QWEN_MODEL",
    },
}


@dataclass(frozen=True)
class AIConfig:
    provider: str
    label: str
    api_url: str
    model: str
    api_key: str


def _dotenv(path: Path) -> dict[str, str]:
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _value(name: str, environment: dict[str, str], file_values: dict[str, str]) -> str:
    return str(environment.get(name) or file_values.get(name) or "").strip()


def _chat_url(value: str) -> str:
    value = value.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return value + "/chat/completions"


def load_ai_config(
    env_file: Path = ENV_FILE,
    environment: dict[str, str] | None = None,
    legacy_key_file: Path = LEGACY_DEEPSEEK_KEY_FILE,
) -> AIConfig:
    """Resolve one provider from process variables and the project .env file."""
    environment = os.environ if environment is None else environment
    file_values = _dotenv(Path(env_file))
    provider = _value("AI_PROVIDER", environment, file_values).lower() or "deepseek"
    if provider not in PROVIDERS:
        supported = "、".join(PROVIDERS)
        raise RuntimeError(f"不支持的 AI_PROVIDER：{provider}；可选值为 {supported}")
    defaults = PROVIDERS[provider]
    key = _value("AI_API_KEY", environment, file_values) or _value(defaults["key_name"], environment, file_values)
    if not key and provider == "deepseek":
        try:
            key = legacy_key_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    if not key:
        raise RuntimeError(f"未配置{defaults['label']} API Key（{defaults['key_name']}）")
    base_url = (
        _value("AI_BASE_URL", environment, file_values)
        or _value(defaults["base_name"], environment, file_values)
        or defaults["api_url"]
    )
    model = (
        _value("AI_MODEL", environment, file_values)
        or _value(defaults["model_name"], environment, file_values)
        or defaults["model"]
    )
    return AIConfig(provider, defaults["label"], _chat_url(base_url), model, key)


def active_provider_label(env_file: Path = ENV_FILE, environment: dict[str, str] | None = None) -> str:
    """Return a display label without requiring a configured API key."""
    environment = os.environ if environment is None else environment
    provider = _value("AI_PROVIDER", environment, _dotenv(Path(env_file))).lower() or "deepseek"
    return PROVIDERS.get(provider, {}).get("label", "AI 服务商")


def chat_completion(
    messages,
    *,
    temperature: float,
    max_tokens: int,
    timeout: float = 60,
    json_object: bool = False,
    config: AIConfig | None = None,
) -> str:
    """Send a non-streaming chat request and return the assistant text."""
    config = config or load_ai_config()
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}
    elif config.provider == "qwen":
        payload["enable_thinking"] = False
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    request = Request(
        config.api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + config.api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", str(error))
        except Exception:
            detail = str(error)
        raise RuntimeError(f"{config.label} 请求失败：{detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"无法连接{config.label}：{error.reason}") from error
    try:
        answer = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        detail = result.get("error", {}).get("message", "接口返回格式不完整") if isinstance(result, dict) else "接口返回格式不完整"
        raise RuntimeError(f"{config.label} 请求失败：{detail}") from error
    if not answer:
        raise RuntimeError(f"{config.label} 没有返回内容")
    return answer
