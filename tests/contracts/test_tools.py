import pytest
from pydantic import ValidationError
from industriax.contracts import tools
from industriax.contracts.tools import (
    DocSearchItem, MemoryWriteRequest, WriteToolRequest,
)
from industriax.contracts.meta import DataLevel, DataDomain, Provenance


def test_read_item_carries_meta():
    item = DocSearchItem(
        chunk="x", data_level=DataLevel.GENERAL, data_domain=DataDomain.EXTERNAL,
        source=Provenance(doc_id="d", version="v1", section="1"),
    )
    assert item.data_level == DataLevel.GENERAL


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
