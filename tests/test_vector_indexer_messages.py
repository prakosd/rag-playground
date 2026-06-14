from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_WARNING
from vector_indexer import messages


def test_skipped_unsupported_file_is_warning_with_params() -> None:
    message = messages.skipped_unsupported_file("notes.pdf")
    assert message.code == messages.CODE_SKIPPED_UNSUPPORTED_FILE
    assert message.severity == SEVERITY_WARNING
    assert message.params == {"file": "notes.pdf"}
    assert "notes.pdf" in str(message)


def test_classify_model_unavailable_detects_missing_openai_key() -> None:
    message = messages.classify_model_unavailable(
        "OPENAI_API_KEY is not configured for OpenAI embeddings."
    )
    assert message.code == messages.CODE_MISSING_OPENAI_KEY
    assert message.severity == SEVERITY_ERROR


def test_classify_model_unavailable_detects_missing_aws_credentials() -> None:
    message = messages.classify_model_unavailable(
        "AWS credentials are not configured for Amazon Titan embeddings."
    )
    assert message.code == messages.CODE_MISSING_AWS_CREDENTIALS
    assert message.severity == SEVERITY_ERROR


def test_classify_model_unavailable_falls_back_to_generic() -> None:
    message = messages.classify_model_unavailable("no provider configured")
    assert message.code == messages.CODE_MODEL_UNAVAILABLE
    assert "no provider configured" in str(message)


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
