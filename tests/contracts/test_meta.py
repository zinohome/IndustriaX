import pytest
from pydantic import ValidationError
from industriax.contracts.meta import (
    DataLevel, DataDomain, Provenance, MetaFields, max_level,
)

def test_level_ordering():
    assert DataLevel.GENERAL < DataLevel.IMPORTANT < DataLevel.CORE

def test_metafields_requires_source():
    with pytest.raises(ValidationError):
        MetaFields(data_level=DataLevel.GENERAL, data_domain=DataDomain.RND)

def test_datalevel_total_ordering():
    assert DataLevel.CORE > DataLevel.GENERAL
    assert DataLevel.GENERAL <= DataLevel.IMPORTANT
    assert DataLevel.CORE >= DataLevel.CORE
    assert not (DataLevel.IMPORTANT > DataLevel.CORE)

def test_datalevel_hashable_and_dict_key():
    d = {DataLevel.GENERAL: 0, DataLevel.IMPORTANT: 1, DataLevel.CORE: 2}
    assert d[DataLevel.CORE] == 2
    s = {DataLevel.GENERAL, DataLevel.IMPORTANT, DataLevel.CORE}
    assert len(s) == 3

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
