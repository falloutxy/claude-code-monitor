#!/usr/bin/env python3
"""
Claude Code API 路由代理
根据请求体中的 model 字段，自动分发到不同的后端 API

使用方式：
  python3 ~/claude-monitor/proxy.py

配置 ~/.claude/settings.json：
  ANTHROPIC_BASE_URL = http://localhost:7843
  ANTHROPIC_MODEL = qwen3-coder-plus   ← 默认模型（可在 Claude Code 内用 /model 切换）
"""

import json
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 7843

# ---- 路由规则：model 关键词 → (base_url, api_key) ----
ROUTES = {
    "minimax": {
        "base_url": "https://api.minimaxi.com/anthropic",
        "api_key":  "sk-cp-iXP6J7pilT1UaJSwtCyMiM3PKvVnh0jGZRPSksrYEgKyYT3l0K3u2CscxrJzTkj06k5bQtedf4iGRPBBOyUfgXklNjReWa3lReYNmlvWmOzsPNBUNhWDQiQ",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
        "api_key":  "sk-92117dbb7f8f488f8590568b9a648c59",
    },
    "glm": {
        "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
        "api_key":  "sk-92117dbb7f8f488f8590568b9a648c59",
    },
    "qwq": {
        "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
        "api_key":  "sk-92117dbb7f8f488f8590568b9a648c59",
    },
    "kimi": {
        "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
        "api_key":  "sk-92117dbb7f8f488f8590568b9a648c59",
    },
}

# 默认路由（model 不匹配任何关键词时）
DEFAULT_ROUTE = ROUTES["qwen"]


def get_route(model: str) -> dict:
    model_lower = (model or "").lower()
    for keyword, route in ROUTES.items():
        if keyword in model_lower:
            return route
    return DEFAULT_ROUTE


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        model = getattr(self, "_model", "?")
        backend = getattr(self, "_backend", "?")
        print(f"[Proxy] {self.command} {self.path} → {backend} (model={model})")

    def do_POST(self):
        # 1. 读取请求体
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length else b""

        # 2. 解析 model 字段，选择路由
        model = ""
        try:
            body_json = json.loads(body_bytes)
            model = body_json.get("model", "")
        except Exception:
            body_json = {}

        route = get_route(model)
        self._model = model
        self._backend = route["base_url"]

        # 3. 拼接目标 URL：把本地路径透传给后端
        target_url = route["base_url"] + self.path  # e.g. /v1/messages

        # 4. 构建转发请求
        req_headers = {
            "Content-Type": "application/json",
            "x-api-key": route["api_key"],
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
        }
        # 透传部分原始头（如 anthropic-beta）
        for h in ("anthropic-beta", "accept"):
            if h in self.headers:
                req_headers[h] = self.headers[h]

        req = urllib.request.Request(
            url=target_url,
            data=body_bytes,
            headers=req_headers,
            method="POST",
        )

        # 5. 转发，处理流式响应
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                # 透传响应头
                for key, val in resp.headers.items():
                    if key.lower() in ("content-type", "transfer-encoding",
                                       "x-request-id", "anthropic-version"):
                        self.send_header(key, val)
                self.end_headers()

                # 流式分块转发
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
            print(f"[Proxy] ❌ HTTP {e.code}: {err_body[:200]}")

        except Exception as e:
            msg = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            print(f"[Proxy] ❌ 异常: {e}")

    def do_GET(self):
        # 健康检查
        if self.path == "/health":
            body = json.dumps({
                "status": "ok",
                "port": PORT,
                "routes": {k: v["base_url"] for k, v in ROUTES.items()}
            }, indent=2, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"✅ Claude Code API 路由代理已启动")
    print(f"📡 监听端口: {PORT}")
    print(f"🔀 路由规则:")
    for kw, r in ROUTES.items():
        print(f"    *{kw}*  →  {r['base_url']}")
    print(f"🌐 健康检查: http://localhost:{PORT}/health")
    print(f"⌨️  Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
