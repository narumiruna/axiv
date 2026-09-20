import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from axiv.models.events import Event
from axiv.models.events import EventsResponse
from axiv.models.paper import PaperComment
from axiv.models.paper import PaperComments
from axiv.models.paper import PaperPreview
from axiv.models.paper import SimilarPapers
from axiv.models.search import FullTextSearchResult
from axiv.models.search import FullTextSearchResults
from axiv.models.search import Organization
from axiv.models.search import OrganizationResults
from axiv.models.search import PaperSearchResult
from axiv.models.search import PaperSearchResults

RESPONSES = json.loads((Path(__file__).parent / "fixtures/api/responses.json").read_text())


@pytest.mark.parametrize(
    ("collection_type", "item_type", "fixture"),
    [
        (EventsResponse, Event, "events"),
        (PaperSearchResults, PaperSearchResult, "search_fast"),
        (FullTextSearchResults, FullTextSearchResult, "search_full_text"),
        (OrganizationResults, Organization, "organizations"),
        (PaperComments, PaperComment, "comments"),
        (SimilarPapers, PaperPreview, "similar"),
    ],
)
def test_collections_preserve_concrete_types_json_and_validation(collection_type, item_type, fixture):
    items = [item_type.model_validate(item) for item in RESPONSES[fixture]]
    result = collection_type.from_items(items)

    assert type(result) is collection_type
    assert all(type(item) is item_type for item in result.items)
    assert json.loads(result.model_dump_json()) == {
        "items": [item.model_dump(mode="json") for item in items],
        "count": len(items),
    }
    assert collection_type.from_items([]).model_dump() == {"items": [], "count": 0}
    assert collection_type.model_json_schema()["title"] == collection_type.__name__
    with pytest.raises(ValidationError):
        collection_type(items=items, count=-1)
    with pytest.raises(ValidationError):
        collection_type(items=items, count=1, unknown=True)
    with pytest.raises(ValidationError):
        collection_type(items=[{}], count=1)
