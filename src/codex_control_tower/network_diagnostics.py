"""Manual, bounded network diagnostics with optional Mihomo integration."""

from __future__ import annotations

import concurrent.futures
import http.client
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SERVICES = {
    "Codex": "https://api.openai.com/v1/models",
    "GitHub": "https://github.com/",
    "Hugging Face": "https://huggingface.co/",
}
_RESULT_CACHE = {}


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path, timeout=2):
        super().__init__("localhost", timeout=timeout); self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout); self.sock.connect(self.socket_path)


def _mihomo_processes():
    rows = []
    for directory in Path("/proc").glob("[0-9]*"):
        try:
            parts = [part.decode(errors="ignore") for part in (directory / "cmdline").read_bytes().split(b"\0") if part]
        except OSError:
            continue
        command = " ".join(parts).lower()
        if "mihomo" not in command and "clash" not in command:
            continue
        rows.append(parts)
    return rows


def _secret_from(parts):
    candidates = []
    for flag in ("-f", "--config"):
        if flag in parts and parts.index(flag) + 1 < len(parts):
            candidates.append(Path(parts[parts.index(flag) + 1]))
    for flag in ("-d", "--dir"):
        if flag in parts and parts.index(flag) + 1 < len(parts):
            root = Path(parts[parts.index(flag) + 1]); candidates.extend((root / "config.yaml", root / "config.yml"))
    for path in candidates:
        try:
            match = re.search(r"(?m)^secret\s*:\s*['\"]?([^'\"\s#]+)", path.read_text(encoding="utf-8"))
            if match:
                return match.group(1)
        except (OSError, UnicodeError):
            pass
    return ""


def discover_controller():
    for parts in reversed(_mihomo_processes()):
        for flag in ("-ext-ctl-unix", "--external-controller-unix"):
            if flag in parts and parts.index(flag) + 1 < len(parts):
                path = parts[parts.index(flag) + 1]
                if Path(path).exists():
                    return {"kind": "unix", "address": path, "secret": _secret_from(parts)}
    for port in (9090, 9097):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.15):
                return {"kind": "tcp", "address": f"127.0.0.1:{port}", "secret": ""}
        except OSError:
            pass
    return None


def controller_request(path, method="GET", payload=None, timeout=2):
    controller = discover_controller()
    if not controller:
        raise ConnectionError("未发现 Mihomo 控制接口")
    headers = {"Accept": "application/json"}; body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8"); headers["Content-Type"] = "application/json"
    if controller.get("secret"):
        headers["Authorization"] = "Bearer " + controller["secret"]
    if controller["kind"] == "unix":
        connection = UnixHTTPConnection(controller["address"], timeout)
    else:
        connection = http.client.HTTPConnection(controller["address"], timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers); response = connection.getresponse(); response_body = response.read()
        if response.status >= 400:
            raise ConnectionError(f"Mihomo 控制接口返回 HTTP {response.status}")
        return json.loads(response_body or b"{}")
    finally:
        connection.close()


def controller_json(path, timeout=2):
    return controller_request(path, timeout=timeout)


def mihomo_snapshot():
    processes = _mihomo_processes(); result = {"running": bool(processes), "node": "", "tun": None, "controller": False}
    if not processes:
        return result
    try:
        proxies = controller_json("/proxies", .8).get("proxies", {})
        preferred = next((value for name, value in proxies.items() if "节点选择" in name and value.get("now")), None)
        if not preferred:
            preferred = next((value for value in proxies.values() if value.get("type") == "Selector" and value.get("now") not in (None, "DIRECT", "REJECT")), None)
        if not preferred:
            preferred = proxies.get("GLOBAL")
        result["node"] = (preferred or {}).get("now", ""); result["controller"] = True
        configs = controller_json("/configs", .8); tun = configs.get("tun")
        result["tun"] = bool(tun.get("enable")) if isinstance(tun, dict) else None
    except Exception:
        pass
    return result


def _proxy_opener():
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=.2):
            proxy = "http://127.0.0.1:7890"
            return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy})), True
    except OSError:
        return urllib.request.build_opener(), False


def _service_check(item):
    name, url = item; opener, proxied = _proxy_opener(); started = time.monotonic()
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FlowDeck-network-check/1.0"})
    try:
        with opener.open(request, timeout=6) as response:
            status = response.status
        ok = status < 500
    except urllib.error.HTTPError as error:
        status = error.code; ok = status < 500
    except Exception:
        return name, {"ok": False, "latency": None, "status": None, "proxied": proxied}
    return name, {"ok": ok, "latency": round((time.monotonic() - started) * 1000), "status": status, "proxied": proxied}


def _connection_routes():
    try:
        rows = controller_json("/connections", 1).get("connections", [])
    except Exception:
        return {}
    result = {}
    domains = {"Codex": ("openai.com", "chatgpt.com"), "GitHub": ("github.com", "githubusercontent.com"), "Hugging Face": ("huggingface.co",), "SSH": ()}
    for name, suffixes in domains.items():
        candidates = []
        for row in rows:
            meta = row.get("metadata") or {}; host = str(meta.get("host") or meta.get("destinationIP") or "").lower(); process = str(meta.get("process") or meta.get("processPath") or "").lower()
            matched = any(host.endswith(suffix) for suffix in suffixes) if suffixes else any(token in process for token in ("ssh", "scp", "rsync"))
            if matched:
                chains = row.get("chains") or []; candidates.append({"host": host, "rule": row.get("rule") or "未知规则", "chain": " → ".join(reversed(chains)) if chains else "DIRECT", "process": process})
        if candidates:
            result[name] = candidates[-1]
    return result


def diagnose_network():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        checks = dict(executor.map(_service_check, SERVICES.items()))
    return {"mihomo": mihomo_snapshot(), "services": checks, "routes": _connection_routes(),
            "terminal_proxy": bool(any(os.environ.get(key) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")))}


def benchmark_current_route(attempts=3):
    cached = _RESULT_CACHE.get("speed")
    if cached and time.monotonic() - cached[0] < 600:
        return {**cached[1], "cached": True}
    opener, proxied = _proxy_opener(); downloads = []; failures = 0; ttfbs = []
    for _ in range(attempts):
        request = urllib.request.Request("https://speed.cloudflare.com/__down?bytes=1000000", headers={"User-Agent": "FlowDeck-speed-test/1.0"})
        started = time.monotonic()
        try:
            with opener.open(request, timeout=12) as response:
                first = response.read(1); first_at = time.monotonic(); data = first + response.read(999999)
            elapsed = max(.001, time.monotonic() - started); downloads.append(len(data) / elapsed); ttfbs.append((first_at - started) * 1000)
        except Exception:
            failures += 1
    upload_speed = None
    try:
        payload = b"0" * 131072; request = urllib.request.Request("https://speed.cloudflare.com/__up", data=payload, method="POST", headers={"Content-Type": "application/octet-stream", "User-Agent": "FlowDeck-speed-test/1.0"}); started = time.monotonic()
        with opener.open(request, timeout=12) as response:
            response.read(64)
        upload_speed = len(payload) / max(.001, time.monotonic() - started)
    except Exception:
        failures += 1
    average = sum(downloads) / len(downloads) if downloads else None
    stability = (1 - ((max(downloads) - min(downloads)) / average)) * 100 if len(downloads) > 1 and average else None
    result = {"proxied": proxied, "node": mihomo_snapshot().get("node"), "download": average, "upload": upload_speed,
              "ttfb": sum(ttfbs) / len(ttfbs) if ttfbs else None, "stability": max(0, stability) if stability is not None else None,
              "failure_percent": round(failures / (attempts + 1) * 100)}
    _RESULT_CACHE["speed"] = (time.monotonic(), result); return result


def _selector_group(proxies, service):
    hints = ("AI网站", "AI") if service == "Codex" else ("节点选择", "Proxy", "代理")
    for hint in hints:
        match = next(((name, value) for name, value in proxies.items() if hint.lower() in name.lower() and value.get("type") == "Selector" and value.get("all")), None)
        if match:return match
    match = next(((name, value) for name, value in proxies.items() if value.get("type") == "Selector" and value.get("all") and name != "GLOBAL"), None)
    return match or (None, None)


def _group_leaves(proxies, group, seen=None):
    seen = set(seen or ())
    if group in seen:return []
    seen.add(group); value = proxies.get(group) or {}
    if value.get("type") not in ("Selector", "URLTest", "Fallback", "LoadBalance"):
        return [] if value.get("alive") is False or group in ("DIRECT", "REJECT") else [group]
    rows = []
    for child in value.get("all") or []:rows.extend(_group_leaves(proxies, child, seen))
    return list(dict.fromkeys(rows))


def recommend_nodes(services=None, limit=12):
    services = tuple(services or ("Codex", "GitHub", "Hugging Face")); cache_key = "recommend:" + ",".join(services)
    cached = _RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 600:
        return {**cached[1], "_cached": True}
    proxies = controller_json("/proxies", 2).get("proxies", {})
    targets = {"Codex": "https://api.openai.com", "GitHub": "https://github.com", "Hugging Face": "https://huggingface.co"}
    jobs = []
    for service in services:
        group_name, group = _selector_group(proxies, service)
        leaves = []
        for name in _group_leaves(proxies, group_name):
            value = proxies.get(name) or {}; history = value.get("history") or []; delay = next((item.get("delay") for item in reversed(history) if item.get("delay")), 99999); leaves.append((delay, name))
        for _, node in sorted(leaves)[:limit]:jobs.append((service, group_name, node, targets[service]))
    def test(job):
        service, group, node, url = job; path = "/proxies/" + urllib.parse.quote(node, safe="") + "/delay?" + urllib.parse.urlencode({"url": url, "timeout": 3000})
        try:return service, group, node, int(controller_json(path, 5).get("delay") or 0)
        except Exception:return service, group, node, 0
    result = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(jobs) or 1)) as executor:
        for service, group, node, delay in executor.map(test, jobs):
            if delay and (service not in result or delay < result[service]["delay"]):result[service] = {"group": group, "node": node, "delay": delay}
    _RESULT_CACHE[cache_key] = (time.monotonic(), result); return result


def switch_fastest(service):
    result = recommend_nodes((service,)); choice = result.get(service)
    if not choice:raise ConnectionError(f"没有找到适合 {service} 的可用节点")
    path = "/proxies/" + urllib.parse.quote(choice["group"], safe="")
    controller_request(path, method="PUT", payload={"name": choice["node"]}, timeout=3)
    _RESULT_CACHE.clear()
    return {"service": service, **choice}
