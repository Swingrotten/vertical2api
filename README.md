# Vertical Studio to OpenAI API Proxy

一个将 Vertical Studio Claude 模型转换为 OpenAI 兼容 API 的代理服务器。

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 依赖包：`fastapi`, `uvicorn`, `httpx`, `pydantic`

### 安装运行
```bash
# 克隆仓库
git clone https://github.com/Swingrotten/vertical2api.git
cd vertical2api

# 安装依赖
pip install fastapi uvicorn httpx pydantic

# 配置认证令牌
# 编辑 vertical.txt 添加你的 Vertical Studio 令牌

# 启动服务器
python main.py
```

服务器将在 `http://localhost:8000` 启动

## 📝 API 使用

### 列出可用模型
```bash
curl -H "Authorization: Bearer sk-test-key-123456" \
     http://localhost:8000/v1/models
```

### 聊天完成（非流式）
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-test-key-123456" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-4-sonnet-20250514",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'
```

### 流式响应（支持思考模式）
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-test-key-123456" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-4-sonnet-20250514-thinking",
    "messages": [{"role": "user", "content": "解释一下量子计算"}],
    "stream": true
  }'
```

## 🔧 配置文件

### models.json
配置可用的模型映射：
```json
{
  "models": [
    {
      "url": "https://app.verticalstudio.ai/stream/models/claude-4-sonnet.data",
      "modelId": "claude-4-sonnet-20250514"
    }
  ]
}
```

### client_api_keys.json
配置客户端API密钥：
```json
[
  "sk-test-key-123456",
  "sk-your-custom-key"
]
```

### vertical.txt
添加你的 Vertical Studio 认证令牌（原始格式）

## ✨ 功能特性

- ✅ **完全 OpenAI 兼容** - 支持标准 OpenAI API 格式
- ✅ **多模型支持** - Claude 4 Opus & Sonnet
- ✅ **思考模式** - 显示 AI 推理过程
- ✅ **流式响应** - 实时内容传输
- ✅ **多轮对话** - 智能上下文保持
- ✅ **动态会话** - 自动获取 Chat ID
- ✅ **双层认证** - 客户端密钥 + Vertical Studio 令牌
- ✅ **负载均衡** - 多令牌轮询

## 🎯 支持的模型

| 模型 | 描述 |
|------|------|
| `claude-4-opus-20250514` | Claude 4 Opus（标准模式） |
| `claude-4-opus-20250514-thinking` | Claude 4 Opus（思考模式） |
| `claude-4-sonnet-20250514` | Claude 4 Sonnet（标准模式） |
| `claude-4-sonnet-20250514-thinking` | Claude 4 Sonnet（思考模式） |

## 🏗️ 架构设计

```
客户端请求 (OpenAI格式)
       ↓
   API 代理服务器
   ├── 认证验证
   ├── 格式转换
   └── 对话管理
       ↓
Vertical Studio API
       ↓
   Claude 模型响应
       ↓
OpenAI 格式输出
```

## 🔒 安全说明

- 本项目仅用于学习和研究目的
- 请遵守 Vertical Studio 的服务条款
- 保护好你的认证令牌，不要提交到公开仓库
- 生产环境请使用更强的 API 密钥

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**由 [Claude Code](https://claude.ai/code) 辅助开发**