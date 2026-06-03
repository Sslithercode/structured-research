import httpx
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel
from backend import config

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_client: instructor.AsyncInstructor | None = None
_raw_client: AsyncOpenAI | None = None


def _get_client() -> instructor.AsyncInstructor:
    global _client
    if _client is None:
        _client = instructor.from_openai(
            AsyncOpenAI(
                base_url=OPENROUTER_BASE,
                api_key=config.openrouter_key(),
                default_headers={"HTTP-Referer": "https://github.com/structured-research"},
            )
        )
    return _client


def _get_raw_client() -> AsyncOpenAI:
    global _raw_client
    if _raw_client is None:
        _raw_client = AsyncOpenAI(
            base_url=OPENROUTER_BASE,
            api_key=config.openrouter_key(),
            default_headers={"HTTP-Referer": "https://github.com/structured-research"},
        )
    return _raw_client


async def chat(messages: list[dict], role: str = "cheap", json_mode: bool = False) -> str:
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = await _get_raw_client().chat.completions.create(
        model=config.model(role),
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content or ""


async def chat_structured(messages: list[dict], response_model: type[BaseModel], role: str = "cheap") -> BaseModel:
    return await _get_client().chat.completions.create(
        model=config.model(role),
        messages=messages,
        response_model=response_model,
        max_retries=2,
    )


async def embed(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{OPENROUTER_BASE}/embeddings",
            headers={
                "Authorization": f"Bearer {config.openrouter_key()}",
                "HTTP-Referer": "https://github.com/structured-research",
            },
            json={"model": config.model("embeddings"), "input": texts},
        )
        r.raise_for_status()
        data = r.json()["data"]
        return [d["embedding"] for d in sorted(data, key=lambda x: x["index"])]
