#!/usr/bin/env python3
"""Claude Code API 路由代理 - 根据模型名自动分发到不同后端

支持：
  - 阿里百炼（默认）：qwen3.6-plus, qwen3-coder-plus, qwen3-max, qwq-plus 等
  - MiniMax：MiniMax-M2.7
  - Ollama 本地（带前缀）：ollama:模型名（如 ollama:qwopus-9b）
  - Ollama 本地（无前缀）：qwen-opus, qwen-opus-fast 等（直接使用模型名）

400 错误防御：自动剥离 thinking / budget_tokens 参数
"""

import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys
import time

PORT = 7843

# ========== 配置区：替换为你自己的 API Key ==========
MINIMAX_API_KEY = "你的MiniMax_API_Key"   # sk-cp- 开头
BAILIAN_API_KEY = "你的百炼_API_Key"       # sk- 开头
# =====================================================

ROUTES = {
    "minimax": {
        "base_url": "https://api.minimaxi.com/anthropic",
        "api_key": MINIMAX_API_KEY,
        "timeout": 120,
    },
    "ollama": {
        "base_url": "http://localhost:11434",
        "api_key": "ollama",
        "timeout": 300,
    },
}

DEFAULT_ROUTE = {
    "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
    "api_key": BAILIAN_API_KEY,
    "timeout": 120,
}

# 直接命名的 Ollama 本地模型（无需 ollama: 前缀）
# 格式：{"你想用的短名称": "ollama里的完整模型名:tag"}
OLLAMA_LOCAL_MODELS = {
    "qwen-opus": "qwen-opus:latest",
    "qwen-opus-fast": "qwen-opus-fast:latest",
    "qwopus-9b": "qwopus-9b:latest",
    "deepseek-r1:8b": "deepseek-r1:8b",
}


def get_route(model):
    model_lower = (model or "").lower()
    # ollama: 前缀路由（万能方式）
    if model_lower.startswith("ollama:"):
        return ROUTES["ollama"], model[7:]
    # 直接命名的本地 Ollama 模型
    if model_lower in OLLAMA_LOCAL_MODELS:
        return ROUTES["ollama"], OLLAMA_LOCAL_MODELS[model_lower]
    # MiniMax
    if "minimax" in model_lower:
        return ROUTES["minimax"], model
    # 默认 → 百炼
    return DEFAULT_ROUTE, model


def sanitize_body(body_bytes):
    """清理请求体：剥离第三方 API 不兼容的参数，防止 400 错误"""
    try:
        data = json.loads(body_bytes)
    except Exception:
        return body_bytes, ""

    model = data.get("model", "")
    removed = []
    for key in ("thinking", "budget_tokens"):
        if key in data:
            removed.append(f"{key}={data[key]}")
            del data[key]

    route, real_model = get_route(model)
    if real_model != model:
        data["model"] = real_model

    if removed:
        print(f"  ⚠️  已剥离不兼容参数: {', '.join(removed)}")

    return json.dumps(data).encode(), model


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        body, original_model = sanitize_body(body)
        route, _ = get_route(original_model)

        target_url = route["base_url"] + self.path
        host = route["base_url"].split("//")[-1].split("/")[0]
        print(f"[{time.strftime('%H:%M:%S')}] {original_model} → {host}")

        headers = {
            "Content-Type": "application/json",
            "x-api-key": route["api_key"],
            "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
        }
        if "anthropic-beta" in self.headers:
            headers["anthropic-beta"] = self.headers["anthropic-beta"]

        req = urllib.request.Request(url=target_url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=route["timeout"]) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("content-type", "transfer-encoding", "x-request-id"):
                        self.send_header(k, v)
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                print(f"  ✅ OK ({resp.status})")
        except urllib.error.HTTPError as e:
            err = e.read()
            print(f"  ❌ {e.code}: {err[:200].decode('utf-8', errors='replace')}")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
        except Exception as e:
            msg = json.dumps({"error": {"type": "proxy_error", "message": str(e)}}).encode()
            print(f"  ❌ 异常: {e}")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self):
        if self.path == "/health":
            info = {
                "status": "ok",
                "port": PORT,
                "local_ollama": ["qwen-opus (22GB)", "qwen-opus-fast (16GB)", "qwopus-9b (9.5GB)", "ollama:* (万能前缀)"],
                "minimax": ["MiniMax-M2.7"],
                "bailian_default": ["qwen3.6-plus (默认)", "qwen3-max", "qwen3.5-plus", "qwen3-coder-plus", "qwen3.5-omni-plus", "qwq-plus", "kimi-k2.5"],
                "defense": "auto-strip thinking/budget_tokens params",
            }
            body = json.dumps(info, ensure_ascii=False, indent=2).encode()
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
    print(f"✅ 代理启动 | 端口:{PORT} | 默认:百炼(qwen3.6-plus)")
    print(f"   qwen-opus / qwen-opus-fast → localhost:11434")
    print(f"   ollama:*                   → localhost:11434 (万能前缀)")
    print(f"   minimax*                   → api.minimaxi.com")
    print(f"   其他(默认)                  → dashscope.aliyuncs.com")
    print(f"   🛡️  thinking 参数自动剥离已启用")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        sys.exit(0)
