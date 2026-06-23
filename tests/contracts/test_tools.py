import inspect
import pytest
import pydantic
from pydantic import ValidationError
from industriax.contracts import tools
from industriax.contracts.tools import (
    DocSearchItem, GraphImpactResult, MemoryItem,
    MemoryWriteRequest, MemoryForgetRequest, WriteToolRequest,
)
from industriax.contracts.meta import DataLevel, DataDomain, Provenance

# ---- I1: parametrize all three response/item models for MetaFields coverage ----

_META_KWARGS = dict(
    data_level=DataLevel.GENERAL,
    data_domain=DataDomain.EXTERNAL,
    source=Provenance(doc_id="d", version="v1", section="1"),
)

_ITEM_INSTANCES = [
    DocSearchItem(chunk="x", **_META_KWARGS),
    GraphImpactResult(node_id="n1", node_kind="service", **_META_KWARGS),
    MemoryItem(content="mem", **_META_KWARGS),
]


@pytest.mark.parametrize("item", _ITEM_INSTANCES, ids=["DocSearchItem", "GraphImpactResult", "MemoryItem"])
def test_read_item_carries_meta(item):
    assert item.data_level == DataLevel.GENERAL
    assert item.data_domain == DataDomain.EXTERNAL
    assert item.source.doc_id == "d"


def test_write_requires_idempotency_key():
    with pytest.raises(ValidationError):
        MemoryWriteRequest(agent_id="a", content="c", scope="session")  # 缺 key


def test_write_idempotency_key_nonempty():
    with pytest.raises(ValidationError):
        MemoryWriteRequest(agent_id="a", content="c", scope="session", idempotency_key="")


def test_every_write_request_has_idempotency_key():
    for model in tools.WRITE_REQUESTS:
        assert issubclass(model, WriteToolRequest)
        assert "idempotency_key" in model.model_fields


def test_no_readonly_request_has_idempotency_key():
    for model in tools.READ_ONLY_REQUESTS:
        assert "idempotency_key" not in model.model_fields


# ---- m1: MemoryForgetRequest rejects missing idempotency_key ----

def test_memory_forget_requires_idempotency_key():
    with pytest.raises(ValidationError):
        MemoryForgetRequest(agent_id="a", filter={"id": "x"})  # 缺 idempotency_key


# ---- C1: every *Request model must appear in exactly one tuple ----

def test_every_request_model_is_classified():
    """Guard against forgetting to add a new *Request model to READ_ONLY_REQUESTS or WRITE_REQUESTS."""
    all_classified = set(tools.READ_ONLY_REQUESTS) | set(tools.WRITE_REQUESTS)

    # Collect request models defined in this module (not imported ones like MetaFields),
    # whose name ends with "Request", excluding the abstract base WriteToolRequest.
    request_models = {
        obj
        for obj in vars(tools).values()
        if (
            isinstance(obj, type)
            and issubclass(obj, pydantic.BaseModel)
            and obj.__module__ == "industriax.contracts.tools"
            and obj.__name__.endswith("Request")
            and obj is not WriteToolRequest
        )
    }

    for model in request_models:
        in_read = model in set(tools.READ_ONLY_REQUESTS)
        in_write = model in set(tools.WRITE_REQUESTS)
        assert in_read or in_write, (
            f"{model.__name__} is not in READ_ONLY_REQUESTS or WRITE_REQUESTS"
        )
        assert not (in_read and in_write), (
            f"{model.__name__} appears in both READ_ONLY_REQUESTS and WRITE_REQUESTS"
        )
