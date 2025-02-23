import os

import httpx
import openai
from dotenv import load_dotenv

load_dotenv()


async def get_llm_response(prompt: str) -> str:

    async with httpx.AsyncClient(proxy=os.getenv("PROXY_URL", None)) as http_client:
        client = openai.AsyncOpenAI(
            base_url=os.getenv("LLM_API_BASE_URL"), api_key=os.getenv("LLM_API_KEY"), http_client=http_client
        )

        response = await client.chat.completions.create(
            model=os.getenv("LLM_API_MODEL"),
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content
