import os

import httpx
import openai
from dotenv import load_dotenv

load_dotenv()


async def get_llm_response(prompt: str, model: str = None, image_base64: str = None) -> str:
    """
    Получает ответ от LLM модели
    
    Args:
        prompt: Текст запроса
        model: Модель LLM (опционально)
        image_base64: Изображение в формате base64 (опционально)
        
    Returns:
        Ответ от LLM модели
    """
    async with httpx.AsyncClient(proxy=os.getenv("PROXY_URL", None)) as http_client:
        client = openai.AsyncOpenAI(
            base_url=os.getenv("LLM_API_BASE_URL"), api_key=os.getenv("LLM_API_KEY"), http_client=http_client
        )

        # Если модель не указана, используем модель по умолчанию из .env
        llm_model = model if model else os.getenv("LLM_API_MODEL")
        
        # Подготовка сообщений
        messages = []
        
        # Если есть изображение, добавляем его в запрос
        if image_base64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "auto"
                        }
                    }
                ]
            })
        else:
            messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=llm_model,
            messages=messages,
        )

        return response.choices[0].message.content
