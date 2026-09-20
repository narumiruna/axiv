import pytest
from pydantic import ValidationError

from axiv.models.common import ErrorEnvelope
from axiv.models.common import RestSettings
from axiv.models.paper import PaperRecord
from axiv.models.paper import ResolvedPaperIdentifiers
from axiv.models.search import PaperSearchResult


def test_external_models_accept_new_remote_fields_and_aliases() -> None:
    result = PaperSearchResult.model_validate(
        {
            "paperId": "1706.03762",
            "title": "Attention Is All You Need",
            "link": "/abs/1706.03762",
            "snippet": "Transformer architecture",
            "newRemoteField": {"enabled": True},
        }
    )

    assert result.paper_id == "1706.03762"
    assert result.model_dump(mode="json")["paper_id"] == "1706.03762"


def test_external_models_still_require_contract_fields() -> None:
    with pytest.raises(ValidationError):
        PaperSearchResult.model_validate({"paperId": "1706.03762"})


def test_paper_record_preserves_distinct_identifiers() -> None:
    record = PaperRecord.model_validate(
        {
            "type": "public",
            "groupId": "015c9ef4-ac30-768d-928b-847320902575",
            "versionId": "0189b531-a930-7613-9d2e-dd918c8435a5",
            "universalId": "1706.03762",
            "versionLabel": "v7",
            "versionOrder": 7,
            "title": "Attention Is All You Need",
            "abstract": "An abstract.",
        }
    )

    assert record.group_id == "015c9ef4-ac30-768d-928b-847320902575"
    assert record.version_id == "0189b531-a930-7613-9d2e-dd918c8435a5"
    assert record.universal_id == "1706.03762"

    # Preserve this import and conversion for Python consumers even when the CLI no longer needs it.
    identifiers = ResolvedPaperIdentifiers.from_record(record)
    assert identifiers.model_dump() == {
        "universal_id": "1706.03762",
        "group_id": "015c9ef4-ac30-768d-928b-847320902575",
        "version_id": "0189b531-a930-7613-9d2e-dd918c8435a5",
    }
    with pytest.raises(ValidationError):
        ResolvedPaperIdentifiers.model_validate({**identifiers.model_dump(), "unknown": True})


def test_settings_reject_non_production_host_and_invalid_timeout() -> None:
    with pytest.raises(ValidationError):
        RestSettings.model_validate({"base_url": "https://api-dev.alphaxiv.org"})

    with pytest.raises(ValidationError):
        RestSettings(timeout_seconds=0)


def test_strict_output_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"error": {"code": "remote_error", "message": "failed"}, "secret": "no"})
