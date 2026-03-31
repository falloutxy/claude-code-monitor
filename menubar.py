#!/usr/bin/env python3
"""
Claude Code Token Monitor - macOS 状态栏程序
依赖: pip3 install rumps
"""
import rumps
import json
import glob
import os
import subprocess
import threading

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
SERVER_URL   = "http://localhost:7842"
SERVER_SCRIPT = os.path.expanduser("~/claude-monitor/server.py")
MAX_MODELS   = 6   # 最多显示几个模型

# ---- 费用计算（人民币，与 server.py 一致）----
def parse_cost(inp, out, cc, cr, model):
    m = (model or "").lower()
    if "minimax" in m:
        return 0.0                             # Coding Plan 已包月 = ¥0
    elif "qwen3-coder-plus" in m: ip, op = 4.0e-6, 16.0e-6   # ¥4/M ¥16/M
    elif "qwen3-max" in m:        ip, op = 2.5e-6, 10.0e-6   # ¥2.5/M ¥10/M
    elif "qwq" in m:              ip, op = 4.0e-6, 16.0e-6
    elif "qwen3.5-plus" in m:     ip, op = 0.8e-6,  3.2e-6   # ¥0.8/M ¥3.2/M
    else:                         ip, op = 1.0e-6,  4.0e-6
    return (inp + cc * 0.25 + cr * 0.1) * ip + out * op

def fmt(n):
    if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return str(int(n))

def load_stats():
    total_in = total_out = total_cr = 0
    total_cost = today_in = today_out = today_cost = 0.0
    model_stats = {}
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")

    for fpath in glob.glob(os.path.join(PROJECTS_DIR, "**/*.jsonl"), recursive=True):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try: r = json.loads(line)
                    except: continue
                    if r.get("type") != "assistant": continue
                    msg   = r.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage: continue
                    model = msg.get("model", "unknown")
                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cc  = usage.get("cache_creation_input_tokens", 0)
                    cr  = usage.get("cache_read_input_tokens", 0)
                    cost = parse_cost(inp, out, cc, cr, model)
                    total_in   += inp;  total_out  += out
                    total_cr   += cr;   total_cost += cost
                    if r.get("timestamp", "").startswith(today_str):
                        today_in += inp; today_out += out; today_cost += cost
                    if model not in model_stats:
                        model_stats[model] = {"in": 0, "out": 0, "cost": 0.0}
                    model_stats[model]["in"]   += inp
                    model_stats[model]["out"]  += out
                    model_stats[model]["cost"] += cost
        except: continue

    return dict(total_in=total_in, total_out=total_out, total_cr=total_cr,
                total_cost=total_cost, today_in=today_in, today_out=today_out,
                today_cost=today_cost, models=model_stats)


class ClaudeMonitorApp(rumps.App):
    def __init__(self):
        super().__init__(name="ClaudeMonitor", title="🤖 …", quit_button=None)
        self.web_proc = None

        # 预建固定菜单项
        self.item_today  = rumps.MenuItem("📅 今日: —")
        self.item_total  = rumps.MenuItem("📦 总计: —")
        self.item_mdiv   = rumps.MenuItem("── 模型分布 ──")
        self.item_mdiv.set_callback(None)

        # 预建 MAX_MODELS 个模型槽位（隐藏方式：空 title）
        icons = ["🥇", "🥈", "🥉", "   ", "   ", "   "]
        self.model_slots = [rumps.MenuItem(f"{icons[i]}  —") for i in range(MAX_MODELS)]
        for sl in self.model_slots:
            sl.set_callback(None)

        self.item_open    = rumps.MenuItem("🌐 打开监控面板",  callback=self.open_dashboard)
        self.item_server  = rumps.MenuItem("▶ 启动 Web 服务", callback=self.toggle_server)
        self.item_refresh = rumps.MenuItem("🔄 立即刷新",      callback=lambda _: self.do_refresh())
        self.item_quit    = rumps.MenuItem("退出",             callback=self.quit_app)

        self.menu = [
            self.item_today,
            self.item_total,
            None,
            self.item_mdiv,
            *self.model_slots,
            None,
            self.item_open,
            self.item_server,
            None,
            self.item_refresh,
            self.item_quit,
        ]

        rumps.Timer(lambda _: self.do_refresh(), 30).start()
        self.do_refresh()

    # ---- 刷新 ----
    def do_refresh(self):
        threading.Thread(target=self._refresh_thread, daemon=True).start()

    def _refresh_thread(self):
        try:
            s = load_stats()
            self.title = f"🤖 ↑{fmt(s['today_out'])}  ¥{s['today_cost']:.2f}"
            self.item_today.title = (
                f"📅 今日  in:{fmt(s['today_in'])}  out:{fmt(s['today_out'])}  "
                f"· ¥{s['today_cost']:.4f}"
            )
            self.item_total.title = (
                f"📦 总计  in:{fmt(s['total_in'])}  "
                f"· ¥{s['total_cost']:.4f}"
            )
            # 更新模型槽位
            icons = ["🥇", "🥈", "🥉", "  ", "  ", "  "]
            sorted_models = sorted(s["models"].items(), key=lambda x: -x[1]["in"])
            for i, slot in enumerate(self.model_slots):
                if i < len(sorted_models):
                    model, ms = sorted_models[i]
                    short = model if len(model) <= 18 else model[:16] + "…"
                    slot.title = f"{icons[i]} {short}  in:{fmt(ms['in'])} · ¥{ms['cost']:.4f}"
                else:
                    slot.title = ""   # 没有数据的槽位清空
        except Exception as e:
            self.title = "🤖 !"
            self.item_today.title = f"❌ 读取失败: {e}"

    # ---- Web 服务 ----
    def toggle_server(self, _):
        if self.web_proc and self.web_proc.poll() is None:
            self.web_proc.terminate()
            self.web_proc = None
            self.item_server.title = "▶ 启动 Web 服务"
        else:
            self.web_proc = subprocess.Popen(
                ["python3", SERVER_SCRIPT],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.item_server.title = "⏹ 停止 Web 服务"

    def open_dashboard(self, _):
        if not (self.web_proc and self.web_proc.poll() is None):
            self.web_proc = subprocess.Popen(
                ["python3", SERVER_SCRIPT],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self.item_server.title = "⏹ 停止 Web 服务"
            import time; time.sleep(1.5)
        subprocess.Popen(["open", SERVER_URL])

    def quit_app(self, _):
        if self.web_proc and self.web_proc.poll() is None:
            self.web_proc.terminate()
        rumps.quit_application()


if __name__ == "__main__":
    ClaudeMonitorApp().run()
