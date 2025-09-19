import json
import base64
import asyncio
from typing import Optional, AsyncGenerator
import httpx


class VerticalApiClient:
    """Vertical Studio API 客户端"""

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def get_chat_id(self, model_url: str, auth_token: str) -> Optional[str]:
        """获取聊天ID - 暂时使用固定的chat ID进行测试"""
        try:
            # 使用用户提供的真实chat ID进行测试
            fixed_chat_id = "cmfr5nvs312v8ycibc8444ep8"
            print(f"使用固定chat_id进行测试: {fixed_chat_id}")
            return fixed_chat_id

        except Exception as e:
            print(f"获取chat_id时出错: {e}")
            return None

    async def send_message_stream(
        self,
        auth_token: str,
        chat_id: str,
        message: str,
        model_id: str,
        output_reasoning: bool = False,
        system_prompt: str = ""
    ) -> AsyncGenerator[str, None]:
        """发送消息并返回流式响应"""
        try:
            # 使用Cookie头格式（根据教程）
            headers = {
                'Cookie': f'sb-ppdjlmajmpcqpkdmnzfd-auth-token={auth_token}',
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # 根据抓取的实际API格式构建请求payload
            import uuid
            import datetime

            message_obj = {
                "id": str(uuid.uuid4()).replace('-', ''),
                "createdAt": datetime.datetime.utcnow().isoformat() + 'Z',
                "role": "user",
                "content": message,
                "parts": [{"type": "text", "text": message}]
            }

            settings = {
                "modelId": model_id,
                "reasoning": output_reasoning,
                "toneOfVoice": None,
                "webSearch": False,
                "systemPromptPreset": None,
                "customSystemPrompt": system_prompt if system_prompt else None
            }

            payload = {
                "message": message_obj,
                "chat": chat_id,
                "settings": settings
            }

            print(f"发送消息到 Vertical Studio API: {message[:50]}...")

            # 使用抓取到的实际API端点
            api_endpoint = "https://app.verticalstudio.ai/api/chat/prompt/text"

            async with self.http_client.stream(
                'POST',
                api_endpoint,
                headers=headers,
                json=payload,
                timeout=60.0
            ) as response:

                if response.status_code != 200:
                    # 读取错误响应
                    error_content = ""
                    try:
                        async for chunk in response.aiter_bytes():
                            error_content += chunk.decode('utf-8', errors='ignore')
                    except:
                        pass

                    yield f'error: {{"message": "API请求失败: {response.status_code} - {error_content[:200]}"}}'
                    return

                # 处理流式响应 - 根据抓取的实际格式
                buffer = ""
                async for chunk in response.aiter_bytes():
                    buffer += chunk.decode('utf-8', errors='ignore')

                    # 按行处理
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()

                        if line:
                            # 处理Vertical Studio的特殊响应格式
                            if line.startswith('f:'):
                                # 消息开始标识，包含messageId
                                continue
                            elif line.startswith('0:'):
                                # 内容块 - 直接转发
                                yield line
                            elif line.startswith('g:') and output_reasoning:
                                # 推理内容 - 直接转发
                                yield line
                            elif line.startswith('e:'):
                                # 结束信息，包含usage等
                                continue
                            elif line.startswith('d:'):
                                # 最终完成信号
                                yield 'd:{"type": "done"}'
                                return
                            elif line.startswith('8:'):
                                # 元数据信息
                                continue

                # 如果没有收到d:信号，主动发送完成
                yield 'd:{"type": "done"}'

        except Exception as e:
            print(f"发送消息时出错: {e}")
            yield f'error: {{"message": "发送消息失败: {str(e)}"}}'