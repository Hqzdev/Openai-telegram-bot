import asyncio
import json
from typing import AsyncGenerator, Dict, List, Optional, Any
from openai import AsyncOpenAI
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)

class OpenAIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.default_model = settings.openai_default_model
        
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = True,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Generate chat completion with streaming support
        """
        if model is None:
            model = self.default_model
            
        # Add system prompt if provided
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
            
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs
            )
            
            if stream:
                async for chunk in response:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            else:
                yield response.choices[0].message.content
                
        except Exception as e:
            logger.error("OpenAI API error", error=str(e), model=model)
            yield f"Извините, произошла ошибка при обработке запроса: {str(e)}"
    
    async def get_completion_stats(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get completion statistics without streaming
        """
        if model is None:
            model = self.default_model
            
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                **kwargs
            )
            
            return {
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "model": response.model,
                "finish_reason": response.choices[0].finish_reason,
            }
            
        except Exception as e:
            logger.error("OpenAI API error", error=str(e), model=model)
            raise
    
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """
        Rough token counting (approximate)
        """
        # Simple approximation: 1 token ≈ 4 characters for English, 2 for Russian
        return len(text) // 3
    
    def truncate_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        model: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Truncate messages to fit within token limit
        """
        total_tokens = 0
        truncated_messages = []
        
        # Start from the most recent messages
        for message in reversed(messages):
            message_tokens = self.count_tokens(message["content"], model)
            
            if total_tokens + message_tokens <= max_tokens:
                truncated_messages.insert(0, message)
                total_tokens += message_tokens
            else:
                break
                
        return truncated_messages
    
    async def generate_dialog_title(self, first_message: str) -> str:
        """
        Generate a title for the dialog based on the first message
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "Создай краткий заголовок (до 50 символов) для диалога на основе первого сообщения пользователя. Заголовок должен отражать суть вопроса или темы."
                    },
                    {
                        "role": "user",
                        "content": first_message[:200]  # Limit to first 200 chars
                    }
                ],
                max_tokens=20,
                temperature=0.3,
                stream=False
            )
            
            title = response.choices[0].message.content.strip()
            # Clean up title
            title = title.replace('"', '').replace("'", "")
            if len(title) > 50:
                title = title[:47] + "..."
                
            return title
            
        except Exception as e:
            logger.error("Error generating dialog title", error=str(e))
            return "Новый диалог"


# Global service instance
openai_service = OpenAIService()
