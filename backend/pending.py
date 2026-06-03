import asyncio
from dataclasses import dataclass, field


@dataclass
class PendingCombine:
    graph_ids: list[str]
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool = False


@dataclass
class PendingStage:
    request_id: str
    stage: str
    snapshot: dict  # serializable data shown to user before approval
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool = False


# combine_id → PendingCombine
pending_combines: dict[str, PendingCombine] = {}

# "{request_id}:{stage}" → PendingStage
pending_stages: dict[str, PendingStage] = {}
