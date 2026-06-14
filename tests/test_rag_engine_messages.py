from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_WARNING
from rag_engine import messages


def test_model_fallback_echo_is_a_warning() -> None:
    message = messages.model_fallback_echo("gpt-4o", "no credentials")

    assert message.code == messages.CODE_MODEL_FALLBACK_ECHO
    assert message.severity == SEVERITY_WARNING
    assert message.params["requested_model"] == "gpt-4o"


def test_classify_generation_failure_detects_ssl() -> None:
    message = messages.classify_generation_failure("CERTIFICATE_VERIFY_FAILED while connecting")

    assert message.code == messages.CODE_SSL_CERTIFICATE
    assert message.severity == SEVERITY_ERROR


def test_classify_generation_failure_generic() -> None:
    message = messages.classify_generation_failure("some random failure")

    assert message.code == messages.CODE_GENERATION_FAILED
    assert message.severity == SEVERITY_ERROR


def test_index_not_found_is_an_error() -> None:
    message = messages.index_not_found("/tmp/x")

    assert message.code == messages.CODE_INDEX_NOT_FOUND
    assert message.severity == SEVERITY_ERROR
    assert message.params["path"] == "/tmp/x"


def test_no_context_is_a_warning() -> None:
    message = messages.no_context()

    assert message.code == messages.CODE_NO_CONTEXT
    assert message.severity == SEVERITY_WARNING
