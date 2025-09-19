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
            # 暂时使用模拟响应来测试基础功能
            print(f"模拟发送消息: {message[:50]}...")

            # 模拟思考过程（如果请求）
            if output_reasoning:
                yield 'g:"正在分析您的问题..."'
                await asyncio.sleep(0.1)
                yield 'g:"准备生成回复..."'
                await asyncio.sleep(0.1)

            # 模拟主要回复
            if "你好" in message or "hello" in message.lower():
                yield '0:"你好！我是Claude，很高兴为您服务。有什么可以帮助您的吗？"'
            elif "测试" in message or "test" in message.lower():
                yield '0:"测试成功！API代理正在正常工作。"'
            else:
                yield '0:"我收到了您的消息。目前这是一个模拟响应，用于测试API代理的基础功能。"'

            # 发送完成信号
            yield 'd:{"type": "done"}'

        except Exception as e:
            print(f"发送消息时出错: {e}")
            yield f'error: {{"message": "发送消息失败: {str(e)}"}}'