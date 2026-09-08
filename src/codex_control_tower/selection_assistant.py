"""Local selection-assistant transport and DeepSeek client."""
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path


SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "codex-control-tower-selection.sock"
KEY_FILE = Path.home() / ".config/deepseek-tools/api-key"
API_URL = "https://api.deepseek.com/chat/completions"


def create_receiver():
    """Create the non-blocking, user-only local datagram receiver."""
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    receiver.bind(str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o600)
    receiver.setblocking(False)
    return receiver


def receive_requests(receiver):
    requests = []
    while True:
        try:
            raw = receiver.recv(65535)
        except BlockingIOError:
            break
        try:
            item = json.loads(raw.decode("utf-8"))
            mode, text = item.get("mode"), str(item.get("text", "")).strip()
            if mode in ("translate", "explain"):
                requests.append({"mode": mode, "text": text[:20000]})
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return requests


def request_deepseek(mode, text):
    try:
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        key = ""
    if not key:
        raise RuntimeError("没有找到 DeepSeek API Key")
    if mode == "translate":
        prompt = (
            "你是专业翻译引擎。将用户文本准确、自然地翻译成简体中文，保持原文格式和含义。"
            "只输出译文，不解释，不添加引号、前言、注释或 Markdown 标记。专有名词有明确惯用译名时"
            "使用惯用译名，否则保留原文。"
        )
        max_tokens, temperature = 4096, 0
    else:
        prompt = (
            "你是一名简明严谨的中文百科助手。解释用户选中的名词或概念：先给一句话定义，"
            "再说明常见语境，最后给一个易懂例子。控制在 300 字以内，只输出纯文本。"
        )
        max_tokens, temperature = 600, 0.2
    body = json.dumps({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        "thinking": {"type": "disabled"}, "temperature": temperature,
        "max_tokens": max_tokens,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API_URL, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", str(error))
        except Exception:
            message = str(error)
        raise RuntimeError(message) from error
    answer = payload.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not answer:
        raise RuntimeError(payload.get("error", {}).get("message", "接口没有返回内容"))
    return answer

