# Claude Code Token Monitor

一个为 Claude Code 用户打造的实时 Token 用量监控工具，支持 macOS 状态栏和 Web 面板双模式。

## 功能特性

- 🤖 **macOS 状态栏**：实时显示今日 Token 用量和费用，30秒自动刷新
- 🌐 **Web 监控面板**：近24小时趋势图、模型分布、会话列表
- 💰 **正确费用计算**：按官方价格计算人民币费用，支持 MiniMax Coding Plan（¥0）和阿里百炼 Qwen 系列
- ⚡ **零侵入**：直接读取 `~/.claude/projects/` 下的 JSONL 日志，不需要修改 Claude Code

## 支持的模型价格

| 模型 | 输入 | 输出 | 备注 |
|------|------|------|------|
| MiniMax-M2.7 | ¥0 | ¥0 | Coding Plan 包月 |
| qwen3-coder-plus | ¥4/M | ¥16/M | 官方价（≤32K档） |
| qwen3-max | ¥2.5/M | ¥10/M | 官方价（≤32K档） |
| qwen3.5-plus | ¥0.8/M | ¥3.2/M | 官方价 |
| qwq-plus | ¥4/M | ¥16/M | 官方价 |

## 快速开始

### 1. 安装依赖

```bash
pip3 install rumps
```

### 2. 启动状态栏（推荐）

```bash
python3 ~/claude-monitor/menubar.py
```

### 3. 启动 Web 面板

```bash
python3 ~/claude-monitor/server.py
# 浏览器打开 http://localhost:7842
```

## 开机自动启动（LaunchAgent）

```bash
# 修改 plist 中的用户名路径后执行：
cp com.yourname.claude-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.yourname.claude-monitor.plist
```

## 快捷命令（写入 ~/.zshrc）

```bash
alias claude-monitor='open http://localhost:7842 && python3 ~/claude-monitor/server.py'
alias claude-menubar='python3 ~/claude-monitor/menubar.py &'

# API 切换（可选）
alias claude-minimax='cp ~/.claude-profiles/minimax.json ~/.claude/settings.json && echo "✅ 已切换到 MiniMax"'
alias claude-bailian='cp ~/.claude-profiles/bailian.json ~/.claude/settings.json && echo "✅ 已切换到 百炼 qwen3-coder-plus"'
alias claude-which='python3 -c "import json; d=json.load(open(\"$HOME/.claude/settings.json\")); print(\"当前模型:\", d[\"env\"][\"ANTHROPIC_MODEL\"])"'
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `server.py` | Web 服务后端（解析 JSONL + API） |
| `menubar.py` | macOS 状态栏程序 |
| `index.html` | Web 监控面板前端 |
| `com.yaoge.claude-monitor.plist` | LaunchAgent 配置（需修改路径） |

## 截图

> Web 面板与 macOS 状态栏同时运行

## 适配的第三方 API

本工具适配通过第三方 API（非 Anthropic 官方）使用 Claude Code 的场景：

- **阿里百炼 DashScope**：`https://dashscope.aliyuncs.com/apps/anthropic`
- **MiniMax**：`https://api.minimaxi.com/anthropic`

## License

MIT
