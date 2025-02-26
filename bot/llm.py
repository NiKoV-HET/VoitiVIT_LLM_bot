import os

import httpx
import openai
from dotenv import load_dotenv

load_dotenv()


async def get_llm_response(prompt: str, model: str = None) -> str:

    async with httpx.AsyncClient(proxy=os.getenv("PROXY_URL", None)) as http_client:
        client = openai.AsyncOpenAI(
            base_url=os.getenv("LLM_API_BASE_URL"), api_key=os.getenv("LLM_API_KEY"), http_client=http_client
        )

        # Если модель не указана, используем модель по умолчанию из .env
        llm_model = model if model else os.getenv("LLM_API_MODEL")

        response = await client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content
