#!/usr/bin/env python3
"""Claude Code Token Usage Monitor + MCP Manager"""

import json, os, glob, shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

PROJECTS_DIR  = os.path.expanduser("~/.claude/projects")
CLAUDE_JSON   = os.path.expanduser("~/.claude.json")
PORT          = 7842

# ── 费用计算（人民币）──────────────────────────────────────────
def parse_cost(inp, out, cc, cr, model):
    m = (model or "").lower()
    if "minimax" in m:                 return 0.0
    elif "qwen3-coder-plus" in m:      ip, op = 4.0e-6, 16.0e-6
    elif "qwen3-max" in m:             ip, op = 2.5e-6, 10.0e-6
    elif "qwq" in m:                   ip, op = 4.0e-6, 16.0e-6
    elif "qwen3.5-plus" in m or "qwen-plus" in m: ip, op = 0.8e-6, 3.2e-6
    else:                              ip, op = 1.0e-6, 4.0e-6
    return (inp + cc * 0.25 + cr * 0.1) * ip + out * op

def fmt_tok(n):
    if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return str(n)

# ── Token 统计 ────────────────────────────────────────────────
def load_all_sessions():
    sessions, model_stats, hourly = [], {}, {}
    total_in = total_out = total_cc = total_cr = 0
    total_cost = 0.0

    for fpath in glob.glob(os.path.join(PROJECTS_DIR, "**/*.jsonl"), recursive=True):
        sid = os.path.basename(fpath).replace(".jsonl", "")
        s_in = s_out = s_cc = s_cr = 0
        s_cost = 0.0; s_model = "unknown"; s_turns = 0
        s_start = s_last = None; messages = []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try: rec = json.loads(line)
                    except: continue
                    ts_str = rec.get("timestamp", "")
                    ts = None
                    if ts_str:
                        try: ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except: pass
                    if ts:
                        if s_start is None or ts < s_start: s_start = ts
                        if s_last  is None or ts > s_last:  s_last  = ts
                    if rec.get("type") != "assistant": continue
                    msg   = rec.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage: continue
                    model = msg.get("model", "unknown")
                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cc  = usage.get("cache_creation_input_tokens", 0)
                    cr  = usage.get("cache_read_input_tokens", 0)
                    cost = parse_cost(inp, out, cc, cr, model)
                    s_in += inp; s_out += out; s_cc += cc; s_cr += cr
                    s_cost += cost; s_turns += 1
                    if model != "unknown": s_model = model
                    if ts:
                        hk = ts.strftime("%Y-%m-%d %H:00")
                        hourly.setdefault(hk, {"input":0,"output":0,"cost":0.0})
                        hourly[hk]["input"] += inp; hourly[hk]["output"] += out
                        hourly[hk]["cost"]  += cost
                    model_stats.setdefault(model, {"input":0,"output":0,"cost":0.0,"turns":0})
                    model_stats[model]["input"] += inp; model_stats[model]["output"] += out
                    model_stats[model]["cost"]  += cost; model_stats[model]["turns"] += 1
                    messages.append({"ts":ts_str,"model":model,"input":inp,"output":out,
                                     "cache_c":cc,"cache_r":cr,"cost":cost})
        except: continue
        if s_turns > 0:
            total_in += s_in; total_out += s_out; total_cc += s_cc
            total_cr += s_cr; total_cost += s_cost
            sessions.append({"id":sid,"model":s_model,"turns":s_turns,
                "input":s_in,"output":s_out,"cache_creation":s_cc,"cache_read":s_cr,
                "cost":round(s_cost,6),
                "start":s_start.isoformat() if s_start else "",
                "last": s_last.isoformat()  if s_last  else "",
                "messages":messages[-5:]})
    sessions.sort(key=lambda x: x.get("last",""), reverse=True)
    sorted_hours = sorted(hourly.keys())[-24:]
    return {
        "total": {"input":total_in,"output":total_out,"cache_creation":total_cc,
                  "cache_read":total_cr,"cost":round(total_cost,4),
                  "sessions":len(sessions),"currency":"CNY"},
        "model_stats": model_stats,
        "sessions": sessions[:20],
        "hourly": [{"hour":h,**hourly[h]} for h in sorted_hours],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

# ── MCP 管理 ──────────────────────────────────────────────────
def read_claude_json():
    if not os.path.exists(CLAUDE_JSON): return {}
    try:
        with open(CLAUDE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return {}

def write_claude_json(data):
    tmp = CLAUDE_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    shutil.move(tmp, CLAUDE_JSON)

def get_mcp_servers():
    data = read_claude_json()
    servers = data.get("mcpServers", {})
    result = []
    for name, cfg in servers.items():
        result.append({
            "name":    name,
            "command": cfg.get("command", ""),
            "args":    cfg.get("args", []),
            "env":     cfg.get("env", {}),
            "disabled":cfg.get("disabled", False),
        })
    return result

def add_mcp_server(name, command, args, env=None):
    data = read_claude_json()
    data.setdefault("mcpServers", {})
    if name in data["mcpServers"]:
        raise ValueError(f"MCP server '{name}' 已存在")
    data["mcpServers"][name] = {"command": command, "args": args or []}
    if env: data["mcpServers"][name]["env"] = env
    write_claude_json(data)

def delete_mcp_server(name):
    data = read_claude_json()
    if name not in data.get("mcpServers", {}):
        raise KeyError(f"MCP server '{name}' 不存在")
    del data["mcpServers"][name]
    write_claude_json(data)

def toggle_mcp_server(name, disabled: bool):
    data = read_claude_json()
    if name not in data.get("mcpServers", {}):
        raise KeyError(f"MCP server '{name}' 不存在")
    if disabled:
        data["mcpServers"][name]["disabled"] = True
    else:
        data["mcpServers"][name].pop("disabled", None)
    write_claude_json(data)

# ── HTTP 处理 ─────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path

        if p == "/api/stats":
            self._send_json(load_all_sessions())

        elif p == "/api/mcp":
            self._send_json({"servers": get_mcp_servers()})

        elif p == "/" or p == "/index.html":
            html = os.path.join(os.path.dirname(__file__), "index.html")
            with open(html, "rb") as f: body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/mcp":
            try:
                body = self._read_body()
                name    = body.get("name", "").strip()
                command = body.get("command", "").strip()
                args    = body.get("args", [])
                env     = body.get("env", {}) or {}
                if not name or not command:
                    return self._send_json({"error": "name 和 command 不能为空"}, 400)
                add_mcp_server(name, command, args, env if env else None)
                self._send_json({"ok": True, "message": f"已添加 {name}"})
            except ValueError as e:
                self._send_json({"error": str(e)}, 409)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self.send_response(404); self.end_headers()

    def do_DELETE(self):
        p = urlparse(self.path).path
        if p.startswith("/api/mcp/"):
            name = p[len("/api/mcp/"):]
            try:
                delete_mcp_server(name)
                self._send_json({"ok": True, "message": f"已删除 {name}"})
            except KeyError as e:
                self._send_json({"error": str(e)}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self.send_response(404); self.end_headers()

    def do_PATCH(self):
        p = urlparse(self.path).path
        if p.startswith("/api/mcp/") and p.endswith("/toggle"):
            name = p[len("/api/mcp/"):-len("/toggle")]
            try:
                body = self._read_body()
                toggle_mcp_server(name, body.get("disabled", False))
                self._send_json({"ok": True})
            except KeyError as e:
                self._send_json({"error": str(e)}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"✅ Claude Monitor 已启动  http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
