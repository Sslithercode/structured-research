import json
import os
from pathlib import Path
from dotenv import load_dotenv

_root = Path(__file__).parent.parent
load_dotenv(_root / ".env")
with open(_root / "config.json") as f:
    _cfg = json.load(f)


def model(role: str) -> str:
    return _cfg["models"][role]

def search_cfg() -> dict:
    return _cfg["search"]

def pipeline_cfg() -> dict:
    return _cfg["pipeline"]

def require_combine_approval() -> bool:
    return bool(pipeline_cfg().get("require_combine_approval", False))

def sources_cfg() -> dict:
    return _cfg.get("sources", {})

def trusted_sources() -> list[str]:
    return sources_cfg().get("trusted", [])

def untrusted_sources() -> list[str]:
    return sources_cfg().get("untrusted", [])

def blocked_domains() -> list[str]:
    return sources_cfg().get("blocked_domains", [])

def blocked_authors() -> list[str]:
    return [a.lower() for a in sources_cfg().get("blocked_authors", [])]

def openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")
    return key

def tavily_key() -> str:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY not set in .env")
    return key
