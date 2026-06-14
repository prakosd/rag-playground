from __future__ import annotations

from artifact_store import (
    MESSAGE_SEVERITIES,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    LibraryMessage,
)


def test_str_returns_default_text() -> None:
    message = LibraryMessage(code="x.y", default_text="Something happened.")
    assert str(message) == "Something happened."


def test_defaults_are_info_and_empty_params() -> None:
    message = LibraryMessage(code="x.y", default_text="Hi")
    assert message.severity == SEVERITY_INFO
    assert message.params == {}


def test_as_dict_is_json_shaped() -> None:
    message = LibraryMessage(
        code="vector.embedding_fallback",
        default_text="Falling back.",
        params={"model": "m"},
        severity=SEVERITY_WARNING,
    )
    assert message.as_dict() == {
        "code": "vector.embedding_fallback",
        "text": "Falling back.",
        "severity": "warning",
        "params": {"model": "m"},
    }


def test_as_dict_copies_params() -> None:
    params = {"file": "a.md"}
    message = LibraryMessage(code="x.y", default_text="t", params=params)
    snapshot = message.as_dict()
    params["file"] = "changed"
    assert snapshot["params"] == {"file": "a.md"}


def test_is_frozen() -> None:
    message = LibraryMessage(code="x.y", default_text="t")
    try:
        message.code = "z"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("LibraryMessage should be immutable")


def test_severity_constants_registered() -> None:
    assert {SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR} == MESSAGE_SEVERITIES
