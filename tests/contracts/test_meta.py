import pytest
from industriax.contracts.meta import (
    DataLevel, DataDomain, Provenance, MetaFields, max_level,
)

def test_level_ordering():
    assert DataLevel.GENERAL < DataLevel.IMPORTANT < DataLevel.CORE

def test_metafields_requires_source():
    with pytest.raises(Exception):
        MetaFields(data_level=DataLevel.GENERAL, data_domain=DataDomain.RND)

def test_max_level_picks_highest():
    items = [
        MetaFields(data_level=DataLevel.GENERAL, data_domain=DataDomain.EXTERNAL,
                   source=Provenance(doc_id="d1", version="v1", section="1")),
        MetaFields(data_level=DataLevel.IMPORTANT, data_domain=DataDomain.RND,
                   source=Provenance(doc_id="d2", version="v1", section="2")),
    ]
    assert max_level(items) == DataLevel.IMPORTANT

def test_max_level_empty_defaults_general():
    assert max_level([]) == DataLevel.GENERAL
