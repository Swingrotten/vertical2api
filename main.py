import json
import time
import uuid
import threading
import hashlib
import urllib3
from collections import OrderedDict
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
import uvicorn

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from vertical_client import VerticalApiClient

# Configuration
CONVERSATION_CACHE_MAX_SIZE = 100
DEFAULT_REQUEST_TIMEOUT = 30.0

# Global variables
VALID_CLIENT_KEYS: set = set()
VERTICAL_AUTH_TOKENS: list = []
current_vertical_token_index: int = 0
token_rotation_lock = threading.Lock()
models_data: Dict[str, Any] = {}
http_client: Optional[httpx.AsyncClient] = None
vertical_api_client: Optional[VerticalApiClient] = None
conversation_cache: OrderedDict = OrderedDict()
cache_lock = threading.Lock()

# Pydantic Models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str

class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelInfo]

class ChatCompletionChoice(BaseModel):
    message: ChatMessage
    index: int = 0
    finish_reason: str = "stop"

class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

class StreamChoice(BaseModel):
    delta: Dict[str, Any] = Field(default_factory=dict)
    index: int = 0
    finish_reason: Optional[str] = None

class StreamResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[StreamChoice]

# FastAPI App
app = FastAPI(title="Vertical OpenAI Compatible API")
security = HTTPBearer(auto_error=False)

# Helper functions
def generate_message_fingerprint(role: str, content: str) -> str:
    """生成消息的指纹，用于快速比较"""
    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    return f"{role}:{content_hash}"

def load_models():
    """加载模型配置"""
    try:
        with open("models.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        # 处理数据结构，确保正确格式
        if "data" in raw_data:
            processed_data = raw_data
        elif "models" in raw_data:
            # 转换旧格式到新格式
            processed_models = []
            for model in raw_data["models"]:
                model_entry = {
                    "id": model.get("modelId", ""),
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "vertical-studio",
                    "vertical_model_id": model.get("modelId", ""),
                    "vertical_model_url": model.get("url", "")
                }
                # 创建带 -thinking 后缀的版本
                thinking_entry = model_entry.copy()
                thinking_entry["id"] = f"{model_entry['id']}-thinking"
                thinking_entry["description"] = f"{model_entry['id']} (with thinking steps)"
                
                model_entry["description"] = f"{model_entry['id']} (final answer only)"
                
                processed_models.append(model_entry)
                processed_models.append(thinking_entry)
                
            processed_data = {"data": processed_models}
        else:
            processed_data = {"data": []}
            
        # 为每个模型设置内部标志
        for model in processed_data["data"]:
            model["output_reasoning_flag"] = model["id"].endswith("-thinking")
            if model.get("created", 0) == 0:
                model["created"] = int(time.time())
                
        return processed_data
    except Exception as e:
        print(f"加载 models.json 时出错: {e}")
        return {"data": []}

def load_client_api_keys():
    """加载客户端 API 密钥"""
    global VALID_CLIENT_KEYS
    try:
        with open("client_api_keys.json", "r", encoding="utf-8") as f:
            keys = json.load(f)
            if not isinstance(keys, list):
                print("警告: client_api_keys.json 应包含密钥列表")
                VALID_CLIENT_KEYS = set()
                return
            VALID_CLIENT_KEYS = set(keys)
            if not VALID_CLIENT_KEYS:
                print("警告: client_api_keys.json 为空")
            else:
                print(f"成功加载 {len(VALID_CLIENT_KEYS)} 个客户端 API 密钥")
    except FileNotFoundError:
        print("错误: 未找到 client_api_keys.json")
        VALID_CLIENT_KEYS = set()
    except Exception as e:
        print(f"加载 client_api_keys.json 时出错: {e}")
        VALID_CLIENT_KEYS = set()

def load_vertical_auth_tokens():
    """加载 Vertical 认证令牌"""
    global VERTICAL_AUTH_TOKENS
    try:
        with open("vertical.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        loaded_tokens = []
        for line in lines:
            line = line.strip()
            if line:
                parts = line.split("----")
                if len(parts) >= 1:
                    loaded_tokens.append(parts[0])
                    
        VERTICAL_AUTH_TOKENS = loaded_tokens
        if not VERTICAL_AUTH_TOKENS:
            print("警告: vertical.txt 中未找到有效令牌")
        else:
            print(f"成功加载 {len(VERTICAL_AUTH_TOKENS)} 个 Vertical 认证令牌")
            
    except FileNotFoundError:
        print("错误: 未找到 vertical.txt")
        VERTICAL_AUTH_TOKENS = []
    except Exception as e:
        print(f"加载 vertical.txt 时出错: {e}")
        VERTICAL_AUTH_TOKENS = []

def get_model_item(model_id: str) -> Optional[Dict]:
    """根据模型ID获取模型配置"""
    for model in models_data.get("data", []):
        if model.get("id") == model_id:
            return model
    return None

async def authenticate_client(auth: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """客户端认证"""
    if not VALID_CLIENT_KEYS:
        raise HTTPException(status_code=503, detail="服务不可用: 未配置客户端 API 密钥")
    
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=401,
            detail="需要在 Authorization header 中提供 API 密钥",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if auth.credentials not in VALID_CLIENT_KEYS:
        raise HTTPException(status_code=403, detail="无效的客户端 API 密钥")

def get_next_vertical_auth_token() -> str:
    """轮询获取下一个 Vertical 认证令牌"""
    global current_vertical_token_index
    
    if not VERTICAL_AUTH_TOKENS:
        raise HTTPException(status_code=503, detail="服务不可用: 未配置 Vertical 认证令牌")
    
    with token_rotation_lock:
        if not VERTICAL_AUTH_TOKENS:
            raise HTTPException(status_code=503, detail="服务不可用: Vertical 认证令牌不可用")
        token_to_use = VERTICAL_AUTH_TOKENS[current_vertical_token_index]
        current_vertical_token_index = (current_vertical_token_index + 1) % len(VERTICAL_AUTH_TOKENS)
    return token_to_use

# FastAPI 生命周期事件
@app.on_event("startup")
async def startup():
    global models_data, http_client, vertical_api_client
    models_data = load_models()
    load_client_api_keys()
    load_vertical_auth_tokens()
    http_client = httpx.AsyncClient(timeout=None, verify=False, follow_redirects=True)
    vertical_api_client = VerticalApiClient(http_client)
    print("Vertical OpenAI Compatible API 服务器已启动")

@app.on_event("shutdown")
async def shutdown():
    global http_client
    if http_client:
        await http_client.aclose()

# API 端点
@app.get("/v1/models", response_model=ModelList)
async def list_models(_: None = Depends(authenticate_client)):
    """列出可用模型"""
    model_list = []
    for model in models_data.get("data", []):
        model_list.append(ModelInfo(
            id=model.get("id", ""),
            created=model.get("created", int(time.time())),
            owned_by=model.get("owned_by", "vertical-studio")
        ))
    return ModelList(data=model_list)


# 解析 Vertical API 响应内容的辅助函数
def parse_json_string_content(line: str, prefix_len: int, suffix_len: int) -> str:
    """解析 g:"..." 或 0:"..." 格式的内容，并处理JSON转义"""
    content_segment = line[prefix_len:suffix_len]
    try:
        # 将提取的片段视为JSON字符串的值进行解析，以处理所有标准转义序列
        # 例如，如果 content_segment 是 "Hello\\nWorld"，f'"{content_segment}"' 会变成 "\"Hello\\nWorld\""
        # json.loads(...) 会将其转换为 Python 字符串 "Hello\nWorld"
        return json.loads(f'"{content_segment}"')
    except json.JSONDecodeError:
        # 如果解析失败（例如，content_segment 包含未转义的内部引号，使其不是有效的JSON字符串值）
        # 我们回退到只替换双反斜杠引号（原行为），并手动替换 \\n (简单情况)
        # 这是一个保守的回退，更复杂的未处理转义可能依然存在
        print(f"警告: parse_json_string_content 中 JSONDecodeError，回退处理。原始片段: {content_segment[:100]}...") # 打印部分片段以供调试
        temp_content = content_segment.replace('\\\\"', '"') # 处理 \\" -> "
        temp_content = temp_content.replace('\\n', '\n')     # 处理 \n -> 换行符
        temp_content = temp_content.replace('\\t', '\t')     # 处理 \t -> 制表符
        # 可以根据需要添加更多手动替换
        return temp_content
    except Exception as e:
        # 其他未知错误
        print(f"错误: parse_json_string_content 发生意外错误: {e}。原始片段: {content_segment[:100]}...")
        return content_segment # 最坏情况，返回原始未处理片段


# 更新对话缓存
def _update_conversation_cache(
    is_new_cached_conv: bool,
    vertical_chat_id_for_cache: str,
    matched_conv_id_for_cache_update: Optional[str],
    original_request_messages: List[ChatMessage],
    full_assistant_reply_str: str,
    system_prompt_hash_for_cache: int,
    model_url_for_cache: str
):
    """更新对话缓存，维护消息历史指纹"""
    with cache_lock:
        if is_new_cached_conv:
            # 新对话，创建缓存条目
            new_internal_id = str(uuid.uuid4())
            current_fingerprints = [
                generate_message_fingerprint(msg.role, msg.content) 
                for msg in original_request_messages
            ]
            # 添加助手回复的指纹
            current_fingerprints.append(
                generate_message_fingerprint("assistant", full_assistant_reply_str)
            )
            
            conversation_cache[new_internal_id] = {
                "vertical_chat_id": vertical_chat_id_for_cache,
                "vertical_model_url": model_url_for_cache,
                "system_prompt_hash": system_prompt_hash_for_cache,
                "message_fingerprints": current_fingerprints,
                "last_seen": time.time()
            }
            
            # LRU 驱逐
            if len(conversation_cache) > CONVERSATION_CACHE_MAX_SIZE:
                conversation_cache.popitem(last=False)
                
        elif matched_conv_id_for_cache_update:
            # 更新现有对话
            cached_item = conversation_cache[matched_conv_id_for_cache_update]
            
            # 添加最新用户消息的指纹（如果还未添加）
            if original_request_messages:
                last_user_msg = original_request_messages[-1]
                last_user_fingerprint = generate_message_fingerprint(
                    last_user_msg.role, last_user_msg.content
                )
                
                # 检查是否已经存在，避免重复
                if not cached_item["message_fingerprints"] or \
                   cached_item["message_fingerprints"][-1] != last_user_fingerprint:
                    cached_item["message_fingerprints"].append(last_user_fingerprint)
            
            # 添加助手回复的指纹
            cached_item["message_fingerprints"].append(
                generate_message_fingerprint("assistant", full_assistant_reply_str)
            )
            cached_item["last_seen"] = time.time()

# 流式响应适配器
async def openai_stream_adapter(
    api_stream_generator: AsyncGenerator[str, None],
    model_name_for_response: str,
    reasoning_requested: bool,
    vertical_chat_id_for_cache: str,
    is_new_cached_conv: bool,
    matched_conv_id_for_cache_update: Optional[str],
    original_request_messages: List[ChatMessage],
    system_prompt_hash_for_cache: int,
    model_url_for_cache: str
) -> AsyncGenerator[str, None]:
    """将 Vertical API 的流转换为 OpenAI 格式的 SSE"""
    full_assistant_reply_parts = []
    stream_id = f"chatcmpl-{uuid.uuid4().hex}"
    
    try:
        # 首次发送，包含角色信息
        first_chunk_sent = False
        
        async for line in api_stream_generator:
            if line.startswith("error:"):
                # 处理错误
                try:
                    error_data = json.loads(line[6:])
                    error_msg = error_data.get("message", "Unknown error")
                except:
                    error_msg = "Unknown error from Vertical API"
                
                error_resp = StreamResponse(
                    id=stream_id,
                    model=model_name_for_response,
                    choices=[StreamChoice(
                        delta={"role": "assistant", "content": f"错误: {error_msg}"},
                        index=0,
                        finish_reason="stop"
                    )]
                )
                yield f"data: {error_resp.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            delta_payload = None
            
            # 解析 Vertical API 的响应格式
            if line.startswith('0:"') and line.endswith('"'):
                # 主要内容
                final_content = parse_json_string_content(line, 3, -1)
                if not first_chunk_sent:
                    delta_payload = {"role": "assistant", "content": final_content}
                else:
                    delta_payload = {"content": final_content}
                full_assistant_reply_parts.append(final_content)
                
            elif reasoning_requested and line.startswith('g:"') and line.endswith('"'):
                # 推理内容（仅当请求时才包含）
                thinking_content = parse_json_string_content(line, 3, -1)
                # 为缓存添加带前缀的思考内容，但在SSE事件中分离reasoning_content
                full_assistant_reply_parts.append(f"[Thinking]: {thinking_content}")
                if not first_chunk_sent:
                    delta_payload = {"role": "assistant", "reasoning_content": thinking_content}
                else:
                    delta_payload = {"reasoning_content": thinking_content}
                
            elif line.startswith('d:'):
                # 可能是结束信号
                try:
                    event_data = json.loads(line[2:])
                    if event_data.get("type") == "done" or event_data.get("type") == "DONE":
                        # 发送最终的 finish_reason
                        final_resp = StreamResponse(
                            id=stream_id,
                            model=model_name_for_response,
                            choices=[StreamChoice(
                                delta={},
                                index=0,
                                finish_reason="stop"
                            )]
                        )
                        yield f"data: {final_resp.model_dump_json()}\n\n"
                        break
                except:
                    pass
            
            # 如果有内容要发送
            if delta_payload:
                stream_resp = StreamResponse(
                    id=stream_id,
                    model=model_name_for_response,
                    choices=[StreamChoice(
                        delta=delta_payload,
                        index=0
                    )]
                )
                
                if not first_chunk_sent:
                    first_chunk_sent = True
                
                yield f"data: {stream_resp.model_dump_json()}\n\n"
        
        # 更新缓存
        full_assistant_reply = "\n".join(full_assistant_reply_parts)
        _update_conversation_cache(
            is_new_cached_conv,
            vertical_chat_id_for_cache,
            matched_conv_id_for_cache_update,
            original_request_messages,
            full_assistant_reply,
            system_prompt_hash_for_cache,
            model_url_for_cache
        )
        
        # 发送结束标记
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        print(f"流式适配器错误: {e}")
        error_resp = StreamResponse(
            id=stream_id,
            model=model_name_for_response,
            choices=[StreamChoice(
                delta={"role": "assistant", "content": f"内部错误: {str(e)}"},
                index=0,
                finish_reason="stop"
            )]
        )
        yield f"data: {error_resp.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

# 聚合流式响应用于非流式返回
async def aggregate_stream_for_non_stream_response(
    openai_sse_stream: AsyncGenerator[str, None],
    model_name: str
) -> ChatCompletionResponse:
    """聚合流式响应为完整响应"""
    content_parts = []
    reasoning_parts = []
    
    async for sse_line in openai_sse_stream:
        if sse_line.startswith("data: ") and sse_line != "data: [DONE]\n\n":
            try:
                data = json.loads(sse_line[6:].strip())
                if data.get("choices") and len(data["choices"]) > 0:
                    delta = data["choices"][0].get("delta", {})
                    if "content" in delta:
                        content_parts.append(delta["content"])
                    elif "reasoning_content" in delta:
                        reasoning_parts.append(delta["reasoning_content"])
            except:
                pass
    
    # 组合最终内容，如果有推理内容则添加
    combined_parts = []
    if reasoning_parts:
        for part in reasoning_parts:
            combined_parts.append(f"[Thinking]: {part}")
    
    combined_parts.extend(content_parts)
    full_content = "".join(combined_parts)
    
    return ChatCompletionResponse(
        model=model_name,
        choices=[ChatCompletionChoice(
            message=ChatMessage(role="assistant", content=full_content),
            finish_reason="stop"
        )]
    )

# 主要的聊天完成端点
@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    _: None = Depends(authenticate_client)
):
    """创建聊天完成"""
    global vertical_api_client
    
    # 获取模型配置
    model_config = get_model_item(request.model)
    if not model_config:
        raise HTTPException(status_code=404, detail=f"模型 {request.model} 未找到")
    
    # 获取认证令牌
    auth_token = get_next_vertical_auth_token()
    
    # 从模型配置中提取信息
    vertical_model_id = model_config.get("vertical_model_id")
    vertical_model_url = model_config.get("vertical_model_url")
    output_reasoning_active = model_config.get("output_reasoning_flag", False)
    
    if not vertical_model_id or not vertical_model_url:
        raise HTTPException(status_code=500, detail="模型配置不完整")
    
    # 提取系统提示和用户消息
    current_system_prompt_str = ""
    latest_user_message_content = ""
    
    for msg in request.messages:
        if msg.role == "system":
            current_system_prompt_str += msg.content + "\n"
        elif msg.role == "user":
            latest_user_message_content = msg.content
    
    current_system_prompt_str = current_system_prompt_str.strip()
    
    if not latest_user_message_content:
        raise HTTPException(status_code=400, detail="请求中未找到用户消息")
    
    # 生成系统提示哈希
    current_system_prompt_hash = hash(current_system_prompt_str)
    
    # 生成消息指纹（不包括最后一条用户消息）
    prefix_message_fingerprints = []
    for i, msg in enumerate(request.messages[:-1]):  # 排除最后一条消息
        prefix_message_fingerprints.append(
            generate_message_fingerprint(msg.role, msg.content)
        )
    
    # 查找匹配的缓存对话
    matched_conv_id = None
    cached_vertical_chat_id = None
    
    with cache_lock:
        # 从最近使用的开始遍历
        for conv_id, cached_data in reversed(list(conversation_cache.items())):
            if (cached_data["vertical_model_url"] == vertical_model_url and
                cached_data["system_prompt_hash"] == current_system_prompt_hash and
                cached_data["message_fingerprints"][:-1] == prefix_message_fingerprints):  # 比较时排除最后的助手回复
                
                matched_conv_id = conv_id
                cached_vertical_chat_id = cached_data["vertical_chat_id"]
                conversation_cache.move_to_end(conv_id)  # 更新 LRU
                break
    
    # 确定对话流程
    final_vertical_chat_id = None
    message_to_send_to_vertical = ""
    is_new_cached_conversation = False
    
    if cached_vertical_chat_id:
        # 复用现有对话
        final_vertical_chat_id = cached_vertical_chat_id
        message_to_send_to_vertical = latest_user_message_content
        print(f"复用现有对话 chat_id: {final_vertical_chat_id}")
    else:
        # 新对话
        is_new_cached_conversation = True
        new_chat_id = await vertical_api_client.get_chat_id(vertical_model_url, auth_token)
        
        if not new_chat_id:
            raise HTTPException(status_code=500, detail="无法从 Vertical API 获取 chat_id")
        
        final_vertical_chat_id = new_chat_id
        print(f"创建新对话 chat_id: {final_vertical_chat_id}")
        
        # 为新对话构造完整历史
        history_parts = []
        for msg in request.messages:
            if msg.role == "user":
                history_parts.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                history_parts.append(f"Assistant: {msg.content}")
        
        message_to_send_to_vertical = "\n".join(history_parts)
        if not message_to_send_to_vertical:
            message_to_send_to_vertical = latest_user_message_content
    
    # 调用 Vertical API
    api_stream_generator = vertical_api_client.send_message_stream(
        auth_token,
        final_vertical_chat_id,
        message_to_send_to_vertical,
        vertical_model_id,
        output_reasoning_active,
        current_system_prompt_str
    )
    
    # 创建 OpenAI 格式的流
    openai_sse_stream = openai_stream_adapter(
        api_stream_generator,
        request.model,
        output_reasoning_active,
        final_vertical_chat_id,
        is_new_cached_conversation,
        matched_conv_id,
        request.messages,
        current_system_prompt_hash,
        vertical_model_url
    )
    
    # 返回流式或非流式响应
    if request.stream:
        return StreamingResponse(
            openai_sse_stream,
            media_type="text/event-stream"
        )
    else:
        return await aggregate_stream_for_non_stream_response(
            openai_sse_stream,
            request.model
        )

# 主程序入口
if __name__ == "__main__":
    import os
    
    # 创建示例配置文件（如果不存在）
    if not os.path.exists("client_api_keys.json"):
        with open("client_api_keys.json", "w", encoding="utf-8") as f:
            json.dump(["sk-your-custom-key-here"], f, indent=2)
        print("已创建示例 client_api_keys.json 文件")
    
    print("正在启动 Vertical OpenAI Compatible API 服务器...")
    print("端点:")
    print("  GET  /v1/models")
    print("  POST /v1/chat/completions")
    print("\n在 Authorization header 中使用客户端 API 密钥 (Bearer sk-xxx)")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)