# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于Python FastAPI的应用程序，为Vertical Studio的AI模型创建OpenAI兼容的API代理。该应用允许客户端通过标准OpenAI API格式与Claude模型交互，同时将请求路由到Vertical Studio后端。

**状态：完全可用的生产级实现** ✅

## 核心命令

### 运行应用程序
```bash
python main.py
```
服务器将在 `http://0.0.0.0:8000` 启动

### 开发模式（自动重载）
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 测试API端点
```bash
# 测试模型列表
curl -H "Authorization: Bearer sk-test-key-123456" http://localhost:8000/v1/models

# 测试聊天完成
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer sk-test-key-123456" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-4-sonnet-20250514", "messages": [{"role": "user", "content": "你好"}], "stream": false}'
```

## 系统架构

### 核心组件

- **FastAPI应用** (`main.py`): 包含所有逻辑的单文件应用
- **双层认证系统**:
  - 客户端API密钥用于访问代理服务
  - Vertical Studio认证令牌用于后端API调用
- **模型配置**: 基于JSON的模型定义，支持思考/非思考变体
- **对话缓存**: LRU缓存系统维护对话上下文
- **流处理**: 实时流式支持，输出OpenAI SSE格式

### 关键文件

- `main.py`: 主应用程序，包含所有FastAPI端点、认证、缓存和流逻辑
- `vertical_client.py`: Vertical Studio API客户端实现
- `models.json`: 模型配置，映射模型ID到Vertical Studio端点
- `client_api_keys.json`: 有效客户端API密钥数组
- `vertical.txt`: Vertical Studio认证令牌（原始格式）

### 重要类定义

- `ChatCompletionRequest`/`ChatCompletionResponse`: OpenAI兼容的请求/响应模型
- `StreamResponse`/`StreamChoice`: 流式响应格式模型
- `ModelInfo`/`ModelList`: 模型列表端点模型
- `VerticalApiClient`: Vertical Studio API客户端类

### 认证流程

1. 客户端发送请求，Authorization header中包含Bearer token
2. 代理验证客户端API密钥（从`client_api_keys.json`）
3. 代理轮询使用Vertical Studio令牌（从`vertical.txt`）
4. 使用Cookie认证向Vertical Studio发送后端请求：`sb-ppdjlmajmpcqpkdmnzfd-auth-token`

### 对话管理

- **智能缓存**: 基于消息指纹匹配实现对话复用
- **Chat ID动态获取**:
  - GET `{model_url}?forceNewChat=true` 获取202响应
  - 解析JSON重定向数组提取chat ID
- **多轮对话支持**: 自动匹配历史对话，复用chat ID
- **LRU驱逐**: 可配置最大缓存大小 (`CONVERSATION_CACHE_MAX_SIZE`)
- **线程安全**: 缓存操作使用锁保护

### 流处理架构

- **Vertical API格式解析**:
  - `f:` - 消息开始标记
  - `0:"content"` - 主要内容块
  - `g:"reasoning"` - 推理内容（思考模式）
  - `e:` - 结束信息（包含usage）
  - `d:` - 完成信号
  - `8:` - 元数据信息
- **OpenAI SSE转换**: 转换为标准Server-Sent Events格式
- **思考模式**: 支持`reasoning_content`字段显示推理过程
- **双模式支持**: 流式和非流式响应

### Vertical Studio集成细节

- **Chat ID获取**: 解析重定向响应 `"/stream/models/{model}/{chat_id}"`
- **消息格式**: 完整的消息对象包含ID、时间戳、角色、内容和parts
- **设置参数**: 模型ID、推理模式、语音语调、网络搜索、系统提示等
- **Cookie认证**: 使用特定的会话令牌格式

## 配置说明

- **自动配置**: 应用启动时自动创建示例`client_api_keys.json`
- **令牌轮询**: 多令牌轮询，线程安全
- **模型变体**: `-thinking`后缀模型启用推理步骤显示
- **SSL处理**: 禁用SSL验证，支持重定向

## API端点

- `GET /v1/models` - 列出可用模型
- `POST /v1/chat/completions` - 创建聊天完成（完全OpenAI兼容）

## 支持的模型

- `claude-4-opus-20250514` / `claude-4-opus-20250514-thinking`
- `claude-4-sonnet-20250514` / `claude-4-sonnet-20250514-thinking`

## 实现状态

✅ **完全可用** - 所有功能已实现并测试通过
✅ **动态Chat ID** - 实时获取新会话
✅ **多轮对话** - 智能上下文保持
✅ **思考模式** - 完整推理过程显示
✅ **流式响应** - 实时内容传输
✅ **错误处理** - 完善的异常和状态处理