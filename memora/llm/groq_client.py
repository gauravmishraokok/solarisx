import asyncio
import json
import groq
from groq import AsyncGroq
from memora.llm.base import ILLM
from memora.core.errors import LLMRateLimitError, LLMResponseError

class GroqClient(ILLM):
    def __init__(self, api_key: str, model: str = "llama3-70b-8192"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    async def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        # Standard backoff retry profile: wait 1s, then 2s, then 4s on RateLimit exception
        for attempt, delay in enumerate([1, 2, 4]):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content
            except groq.RateLimitError as e:
                if attempt == 2:
                    raise LLMRateLimitError("Groq Rate Limit exceeded") from e
                await asyncio.sleep(delay)
            except Exception as e:
                raise LLMResponseError(f"Groq API Error: {str(e)}") from e

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 1000) -> dict:
        system_prompt = system + "\n\nYou MUST respond with valid JSON only. No markdown, no explanation."
        raw_response = await self.complete(system_prompt, user, max_tokens)
        
        clean_response = raw_response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        elif clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()
        
        try:
            parsed = json.loads(clean_response)
        except json.JSONDecodeError as e:
            raise LLMResponseError(f"Unparseable JSON: {clean_response}") from e
            
        for key in schema.keys():
            if key not in parsed:
                raise LLMResponseError(f"Missing required key '{key}' in JSON response: {clean_response}")
                
        return parsed
