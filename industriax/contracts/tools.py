from __future__ import annotations
from pydantic import BaseModel, Field
from industriax.contracts.meta import MetaFields


class WriteToolRequest(BaseModel):
    """所有有副作用工具的请求基类——强制幂等键。"""
    idempotency_key: str = Field(min_length=1)


# ---- doc-mcp (只读) ----
class DocSearchRequest(BaseModel):
    query: str
    top_k: int = 8
    filters: dict | None = None


class DocSearchItem(MetaFields):
    chunk: str


# ---- graph-mcp (只读) ----
class GraphImpactRequest(BaseModel):
    change_id: str
    max_hops: int = 4


class GraphImpactResult(MetaFields):
    node_id: str
    node_kind: str


# ---- memory-mcp ----
class MemoryRecallRequest(BaseModel):
    agent_id: str
    query: str
    scope: str


class MemoryItem(MetaFields):
    content: str


class MemoryWriteRequest(WriteToolRequest):
    agent_id: str
    content: str
    scope: str


class MemoryForgetRequest(WriteToolRequest):
    agent_id: str
    filter: dict


READ_ONLY_REQUESTS = (DocSearchRequest, GraphImpactRequest, MemoryRecallRequest)
WRITE_REQUESTS = (MemoryWriteRequest, MemoryForgetRequest)
