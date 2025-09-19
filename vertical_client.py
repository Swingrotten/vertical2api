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
        """获取聊天ID"""
        try:
            # 生成一个唯一的聊天ID
            import uuid
            return str(uuid.uuid4())
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
            # 解析base64编码的认证令牌
            if auth_token.startswith('base64-'):
                token_data = json.loads(base64.b64decode(auth_token[7:]).decode('utf-8'))
                access_token = token_data.get('access_token', '')
            else:
                access_token = auth_token

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream'
            }

            # 构建请求payload - 根据Vertical Studio API实际格式调整
            payload = {
                'message': message,
                'stream': True,
                'model': model_id
            }

            if system_prompt:
                payload['system'] = system_prompt

            if output_reasoning:
                payload['include_reasoning'] = True

            print(f"发送消息到 Vertical Studio API: {message[:50]}...")

            # 构建实际的API端点URL - 基于models.json中的URL模式
            # 将 .data 替换为实际的聊天端点
            api_endpoint = f"https://app.verticalstudio.ai/api/chat/stream"

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

                # 处理流式响应
                buffer = ""
                async for chunk in response.aiter_bytes():
                    buffer += chunk.decode('utf-8', errors='ignore')

                    # 按行处理
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()

                        if line:
                            # 处理不同的响应格式
                            if line.startswith('data: '):
                                data_part = line[6:]
                                try:
                                    parsed = json.loads(data_part)

                                    # 根据Vertical Studio的实际响应格式转换
                                    if parsed.get('type') == 'content':
                                        content = parsed.get('content', '')
                                        yield f'0:"{content}"'
                                    elif parsed.get('type') == 'reasoning' and output_reasoning:
                                        reasoning = parsed.get('content', '')
                                        yield f'g:"{reasoning}"'
                                    elif parsed.get('type') == 'done':
                                        yield 'd:{"type": "done"}'
                                        return
                                except json.JSONDecodeError:
                                    # 如果不是JSON，可能是纯文本流
                                    if data_part and data_part != '[DONE]':
                                        yield f'0:"{data_part}"'
                                    elif data_part == '[DONE]':
                                        yield 'd:{"type": "done"}'
                                        return
                            else:
                                # 直接转发其他格式的行
                                if line.startswith('0:"') or line.startswith('g:"') or line.startswith('d:'):
                                    yield line

                # 如果没有收到done信号，主动发送
                yield 'd:{"type": "done"}'

        except Exception as e:
            print(f"发送消息时出错: {e}")
            yield f'error: {{"message": "发送消息失败: {str(e)}"}}'