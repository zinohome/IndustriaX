from __future__ import annotations
from enum import Enum
from pydantic import BaseModel


class DataLevel(str, Enum):
    GENERAL = "一般"
    IMPORTANT = "重要"
    CORE = "核心"

    @property
    def _rank(self) -> int:
        return {"一般": 0, "重要": 1, "核心": 2}[self.value]

    def __lt__(self, other: "DataLevel") -> bool:  # type: ignore[override]
        if not isinstance(other, DataLevel):
            return NotImplemented
        return self._rank < other._rank


class DataDomain(str, Enum):
    RND = "研发"
    PRODUCTION = "生产"
    OPS = "运维"
    MANAGEMENT = "管理"
    EXTERNAL = "外部"


class Provenance(BaseModel):
    doc_id: str
    version: str
    section: str | None = None


class MetaFields(BaseModel):
    data_level: DataLevel
    data_domain: DataDomain
    source: Provenance


def max_level(items: list[MetaFields]) -> DataLevel:
    level = DataLevel.GENERAL
    for it in items:
        if level < it.data_level:
            level = it.data_level
    return level
