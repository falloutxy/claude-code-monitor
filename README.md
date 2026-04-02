# Claude Code Token Monitor

一个为 Claude Code 用户打造的实时 Token 用量监控工具，支持 **macOS 状态栏**、**Web 面板**、以及**多 API 路由代理**三大功能。

> 适用于通过第三方 API（阿里百炼 / MiniMax）使用 Claude Code 的用户。

---

## 功能特性

- 🤖 **macOS 状态栏**：实时显示今日 Token 用量和费用，30 秒自动刷新
- 🌐 **Web 监控面板**：近 24 小时趋势图、按模型统计、会话列表
- 🔀 **多 API 路由代理**：根据模型名自动分发到不同 API，Claude Code 内可自由切换 MiniMax / 百炼所有模型
- 💰 **人民币费用计算**：按官方价格估算，MiniMax Coding Plan 显示 ¥0
- ⚡ **零侵入**：直接读取 `~/.claude/projects/` 下的 JSONL 日志，无需修改 Claude Code

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `server.py` | Web 服务后端，解析 JSONL 日志 + 提供 API |
| `menubar.py` | macOS 状态栏程序（依赖 `rumps`） |
| `index.html` | Web 监控面板前端 |
| `proxy.py` | 多 API 路由代理（端口 7843） |

---

## 快速开始

### 1. 安装依赖

```bash
pip3 install rumps
```

### 2. 克隆仓库

```bash
git clone https://github.com/falloutxy/claude-code-monitor.git ~/claude-monitor
```

### 3. 配置 API Key

编辑 `~/claude-monitor/proxy.py`，替换 `ROUTES` 中的 API Key：

```python
ROUTES = {
    "minimax": {
        "base_url": "https://api.minimaxi.com/anthropic",
        "api_key":  "你的MiniMax_API_Key",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/apps/anthropic",
        "api_key":  "你的百炼API_Key",
    },
    # ...
}
```

### 4. 配置 Claude Code 指向代理

```bash
# 启动代理
python3 ~/claude-monitor/proxy.py &

# 写入 Claude Code 配置
cat << 'EOF' > ~/.claude/settings.json
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "proxy-placeholder",
        "ANTHROPIC_BASE_URL": "http://localhost:7843",
        "ANTHROPIC_MODEL": "qwen3-coder-plus"
    }
}
EOF
```

### 5. 启动 Web 面板

```bash
python3 ~/claude-monitor/server.py &
open http://localhost:7842
```

### 6. 启动状态栏监控

```bash
python3 ~/claude-monitor/menubar.py &
```

---

## 在 Claude Code 内切换模型

代理启动后，直接在 Claude Code 内用 `/model` 命令切换，无需修改任何配置文件：

```
/model qwen3-coder-plus      ← 百炼，编码优化（推荐）
/model MiniMax-M2.7          ← MiniMax Coding Plan
/model qwen3-max             ← 百炼，最强通用
/model qwq-plus              ← 百炼，深度推理
/model kimi-k2.5             ← 百炼，支持图片理解
/model qwen3.5-plus          ← 百炼，支持图片理解
```

---

## 开机自动启动（LaunchAgent）

### 代理路由

新建 `~/Library/LaunchAgents/com.yourname.claude-proxy.plist`（修改路径中的用户名）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yourname.claude-proxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/你的用户名/claude-monitor/proxy.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict><key>Crashed</key><true/></dict>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>StandardOutPath</key>
    <string>/Users/你的用户名/claude-monitor/proxy.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/你的用户名/claude-monitor/proxy.error.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.yourname.claude-proxy.plist
```

### 状态栏监控（同上，将 proxy.py 换成 menubar.py）

---

## 路由规则

| 模型名包含 | 转发到 | 说明 |
|-----------|--------|------|
| `minimax` | `api.minimaxi.com/anthropic` | MiniMax |
| `qwen` | `dashscope.aliyuncs.com/apps/anthropic` | 阿里百炼 |
| `glm` | `dashscope.aliyuncs.com/apps/anthropic` | 智谱（百炼） |
| `qwq` | `dashscope.aliyuncs.com/apps/anthropic` | 阿里百炼 |
| `kimi` | `dashscope.aliyuncs.com/apps/anthropic` | 月之暗面（百炼） |

默认路由（model 不匹配时）：百炼 DashScope

---

## 费用参考（人民币）

| 模型 | 输入 | 输出 | 备注 |
|------|------|------|------|
| MiniMax-M2.7 | ¥0 | ¥0 | Coding Plan 包月 |
| qwen3-coder-plus | ¥4/M tok | ¥16/M tok | 编码优化，≤32K 档 |
| qwen3-max | ¥2.5/M tok | ¥10/M tok | 最强通用，≤32K 档 |
| qwen3.5-plus | ¥0.8/M tok | ¥3.2/M tok | 通用，支持图片 |
| qwq-plus | ¥4/M tok | ¥16/M tok | 深度推理 |

> 以[阿里云百炼官方价格](https://bailian.console.aliyun.com/)为准，阶梯价在 >32K 时上涨。

---

## 常见问题

**Q: 报 API Error 400**  
进入 Claude Code，输入 `/config` → 找到 **Thinking mode** → 改为 `false`

**Q: 代理无响应**  
```bash
curl http://localhost:7843/health
# 检查后重启：
launchctl unload/load ~/Library/LaunchAgents/com.yourname.claude-proxy.plist
```

**Q: python3 路径不对**  
```bash
which python3  # 查找真实路径，填入 plist
```

---

## License

MIT
