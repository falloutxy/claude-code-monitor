#!/usr/bin/env python3
"""Claude Code Token Usage Monitor"""

import json
import os
import glob
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import math

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

def parse_cost(input_tokens, output_tokens, cache_creation, cache_read, model):
    """
    估算费用（人民币）· 价格数据来源：阿里云百炼官方，2026-04

    本地 Ollama 模型（免费）：
      - qwen-opus, qwen-opus-fast, qwopus-9b, deepseek-r1 等 = ¥0

    MiniMax（Coding Plan 包月）：
      - MiniMax-M2.7 = ¥0

    阿里百炼（≤32K Token 档，实时推理，CNY/百万Token）：
      - qwen3.6-plus        : 输入¥2/M   输出¥8/M
      - qwen3-max           : 输入¥2.5/M 输出¥10/M
      - qwen3-coder-plus    : 输入¥4/M   输出¥16/M
      - qwen3.5-plus        : 输入¥0.8/M 输出¥3.2/M
      - qwen3.5-omni-plus   : 输入¥0.8/M 输出¥3.2/M（参考 qwen3.5-plus 档位）
      - qwq-plus            : 输入¥4/M   输出¥16/M
      - kimi-k2.5           : 输入¥2/M   输出¥8/M
      - 其余未知模型         : 输入¥1/M   输出¥4/M（保守估算）

    注：>32K Token 时百炼单价会上涨，此处取 ≤32K 档简化估算。
    """
    model_lower = (model or "").lower()

    # 本地 Ollama 模型：完全免费
    OLLAMA_FREE = ["qwen-opus", "qwopus", "deepseek-r1", "deepseek-v3",
                   "gemini-3", "gpt-oss", "qwen3-vl"]
    if any(kw in model_lower for kw in OLLAMA_FREE):
        return 0.0

    # MiniMax Coding Plan：包月免费
    if "minimax" in model_lower:
        return 0.0

    # 阿里百炼：按官方价格计算
    if "qwen3.6-plus" in model_lower:
        input_price  = 2.0  / 1_000_000
        output_price = 8.0  / 1_000_000
    elif "qwen3-max" in model_lower:
        input_price  = 2.5  / 1_000_000
        output_price = 10.0 / 1_000_000
    elif "qwen3-coder-plus" in model_lower:
        input_price  = 4.0  / 1_000_000
        output_price = 16.0 / 1_000_000
    elif "qwen3.5-omni" in model_lower:
        input_price  = 0.8  / 1_000_000
        output_price = 3.2  / 1_000_000
    elif "qwen3.5-plus" in model_lower or "qwen-plus" in model_lower:
        input_price  = 0.8  / 1_000_000
        output_price = 3.2  / 1_000_000
    elif "qwq" in model_lower:
        input_price  = 4.0  / 1_000_000
        output_price = 16.0 / 1_000_000
    elif "kimi" in model_lower:
        input_price  = 2.0  / 1_000_000
        output_price = 8.0  / 1_000_000
    else:
        input_price  = 1.0  / 1_000_000
        output_price = 4.0  / 1_000_000

    total = (input_tokens + cache_creation * 0.25 + cache_read * 0.1) * input_price \
            + output_tokens * output_price
    return round(total, 6)

def load_all_sessions():
    sessions = []
    total_input = 0
    total_output = 0
    total_cache_creation = 0
    total_cache_read = 0
    total_cost = 0.0
    model_stats = {}
    hourly = {}

    jsonl_files = glob.glob(os.path.join(PROJECTS_DIR, "**/*.jsonl"), recursive=True)

    for fpath in jsonl_files:
        session_id = os.path.basename(fpath).replace(".jsonl", "")
        session_input = 0
        session_output = 0
        session_cache_c = 0
        session_cache_r = 0
        session_cost = 0.0
        session_model = "unknown"
        session_turns = 0
        session_start = None
        session_last = None
        messages = []

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except:
                        continue

                    ts_str = record.get("timestamp", "")
                    ts = None
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except:
                            pass

                    if ts:
                        if session_start is None or ts < session_start:
                            session_start = ts
                        if session_last is None or ts > session_last:
                            session_last = ts

                    if record.get("type") == "assistant":
                        msg = record.get("message", {})
                        usage = msg.get("usage", {})
                        if not usage:
                            continue

                        model = msg.get("model", "unknown")
                        inp = usage.get("input_tokens", 0)
                        out = usage.get("output_tokens", 0)
                        cc = usage.get("cache_creation_input_tokens", 0)
                        cr = usage.get("cache_read_input_tokens", 0)
                        cost = parse_cost(inp, out, cc, cr, model)

                        session_input += inp
                        session_output += out
                        session_cache_c += cc
                        session_cache_r += cr
                        session_cost += cost
                        session_turns += 1
                        if model != "unknown":
                            session_model = model

                        if ts:
                            hour_key = ts.strftime("%Y-%m-%d %H:00")
                            if hour_key not in hourly:
                                hourly[hour_key] = {"input": 0, "output": 0, "cost": 0.0}
                            hourly[hour_key]["input"] += inp
                            hourly[hour_key]["output"] += out
                            hourly[hour_key]["cost"] += cost

                        if model not in model_stats:
                            model_stats[model] = {"input": 0, "output": 0, "cost": 0.0, "turns": 0}
                        model_stats[model]["input"] += inp
                        model_stats[model]["output"] += out
                        model_stats[model]["cost"] += cost
                        model_stats[model]["turns"] += 1

                        messages.append({
                            "ts": ts_str,
                            "model": model,
                            "input": inp,
                            "output": out,
                            "cache_c": cc,
                            "cache_r": cr,
                            "cost": cost,
                        })
        except Exception as e:
            continue

        if session_turns > 0:
            total_input += session_input
            total_output += session_output
            total_cache_creation += session_cache_c
            total_cache_read += session_cache_r
            total_cost += session_cost

            sessions.append({
                "id": session_id,
                "model": session_model,
                "turns": session_turns,
                "input": session_input,
                "output": session_output,
                "cache_creation": session_cache_c,
                "cache_read": session_cache_r,
                "cost": round(session_cost, 6),
                "start": session_start.isoformat() if session_start else "",
                "last": session_last.isoformat() if session_last else "",
                "messages": messages[-5:],
            })

    sessions.sort(key=lambda x: x.get("last", ""), reverse=True)

    sorted_hours = sorted(hourly.keys())[-24:]
    hourly_data = [{"hour": h, **hourly[h]} for h in sorted_hours]

    return {
        "total": {
            "input": total_input,
            "output": total_output,
            "cache_creation": total_cache_creation,
            "cache_read": total_cache_read,
            "cost": round(total_cost, 4),
            "sessions": len(sessions),
            "currency": "CNY",
        },
        "model_stats": model_stats,
        "sessions": sessions[:20],
        "hourly": hourly_data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/api/stats":
            data = load_all_sessions()
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/" or self.path == "/index.html":
            html_path = os.path.join(os.path.dirname(__file__), "index.html")
            with open(html_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = 7842
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"✅ Claude Monitor 已启动")
    print(f"🌐 打开浏览器访问: http://localhost:{port}")
    print(f"⌨️  按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
