from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_WARNING
from vector_indexer import messages


def test_skipped_unsupported_file_is_warning_with_params() -> None:
    message = messages.skipped_unsupported_file("notes.pdf")
    assert message.code == messages.CODE_SKIPPED_UNSUPPORTED_FILE
    assert message.severity == SEVERITY_WARNING
    assert message.params == {"file": "notes.pdf"}
    assert "notes.pdf" in str(message)


def test_embedding_fallback_records_models() -> None:
    message = messages.embedding_fallback(
        requested_model="amazon.titan", local_model="all-MiniLM-L6-v2", detail="no creds"
    )
    assert message.code == messages.CODE_EMBEDDING_FALLBACK
    assert message.params["requested_model"] == "amazon.titan"
    assert message.params["local_model"] == "all-MiniLM-L6-v2"


def test_no_chunks_is_error() -> None:
    message = messages.no_chunks()
    assert message.code == messages.CODE_NO_CHUNKS
    assert message.severity == SEVERITY_ERROR


def test_classify_embedding_failure_detects_ssl() -> None:
    message = messages.classify_embedding_failure(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
    )
    assert message.code == messages.CODE_SSL_CERTIFICATE
    assert message.severity == SEVERITY_ERROR


def test_classify_embedding_failure_generic() -> None:
    message = messages.classify_embedding_failure("disk is full")
    assert message.code == messages.CODE_EMBEDDING_FAILED
    assert "disk is full" in str(message)
