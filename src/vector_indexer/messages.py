"""Stable message codes and builders for the vector_indexer result contract.

Every warning or error a UI sees on an :class:`~vector_indexer.models.IndexingResult`
is a :class:`~artifact_store.LibraryMessage` built here. Each carries a stable
``code`` (which a UI maps to a localized template) plus the structured ``params``
behind it; ``default_text`` is the English shown when no localization exists, so
notebooks, logs, and ``manifest.json`` stay readable.
"""

from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_WARNING, LibraryMessage

__all__ = [
    "CODE_ARCHIVE_EMPTY",
    "CODE_ARCHIVE_UNREADABLE",
    "CODE_CANCELLED_BEFORE_CHUNKING",
    "CODE_CANCELLED_PARTIAL",
    "CODE_CHUNKING_FAILED",
    "CODE_DIMENSION_MISMATCH",
    "CODE_EMBEDDING_FAILED",
    "CODE_EMBEDDING_FALLBACK",
    "CODE_FILE_UNREADABLE",
    "CODE_MODEL_UNAVAILABLE",
    "CODE_NO_CHUNKS",
    "CODE_NO_READABLE_CONTENT",
    "CODE_SKIPPED_UNSUPPORTED_FILE",
    "CODE_SSL_CERTIFICATE",
    "archive_empty",
    "archive_unreadable",
    "cancelled_before_chunking",
    "cancelled_partial",
    "chunking_failed",
    "classify_embedding_failure",
    "dimension_mismatch",
    "embedding_fallback",
    "file_unreadable",
    "model_unavailable",
    "no_chunks",
    "no_readable_content",
    "skipped_unsupported_file",
]

CODE_SKIPPED_UNSUPPORTED_FILE = "vector.skipped_unsupported_file"
CODE_FILE_UNREADABLE = "vector.file_unreadable"
CODE_ARCHIVE_UNREADABLE = "vector.archive_unreadable"
CODE_ARCHIVE_EMPTY = "vector.archive_empty"
CODE_NO_READABLE_CONTENT = "vector.no_readable_content"
CODE_CANCELLED_BEFORE_CHUNKING = "vector.cancelled_before_chunking"
CODE_CANCELLED_PARTIAL = "vector.cancelled_partial"
CODE_CHUNKING_FAILED = "vector.chunking_failed"
CODE_NO_CHUNKS = "vector.no_chunks"
CODE_EMBEDDING_FAILED = "vector.embedding_failed"
CODE_SSL_CERTIFICATE = "vector.ssl_certificate"
CODE_MODEL_UNAVAILABLE = "vector.model_unavailable"
CODE_EMBEDDING_FALLBACK = "vector.embedding_fallback"
CODE_DIMENSION_MISMATCH = "vector.dimension_mismatch"

# Substrings that mark a TLS/SSL certificate failure inside a backend exception.
_SSL_ERROR_SIGNATURES = (
    "certificate_verify_failed",
    "certificate verify failed",
    "sslcertverificationerror",
    "ssl: certificate",
)


def _warn(code: str, text: str, **params: object) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params=params, severity=SEVERITY_WARNING)


def _error(code: str, text: str, **params: object) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params=params, severity=SEVERITY_ERROR)


def skipped_unsupported_file(file: str) -> LibraryMessage:
    return _warn(CODE_SKIPPED_UNSUPPORTED_FILE, f"Skipped unsupported file: {file}", file=file)


def file_unreadable(file: str, detail: str) -> LibraryMessage:
    return _warn(CODE_FILE_UNREADABLE, f"Could not read {file}: {detail}", file=file, detail=detail)


def archive_unreadable(file: str, detail: str) -> LibraryMessage:
    return _warn(
        CODE_ARCHIVE_UNREADABLE,
        f"Could not read archive {file}: {detail}",
        file=file,
        detail=detail,
    )


def archive_empty(file: str) -> LibraryMessage:
    return _warn(CODE_ARCHIVE_EMPTY, f"No .md or .txt files found in {file}", file=file)


def no_readable_content() -> LibraryMessage:
    return _error(
        CODE_NO_READABLE_CONTENT,
        "No readable .md or .txt content was found in the selected inputs.",
    )


def cancelled_before_chunking() -> LibraryMessage:
    return _warn(CODE_CANCELLED_BEFORE_CHUNKING, "Indexing was cancelled before chunking started.")


def chunking_failed(detail: str) -> LibraryMessage:
    return _error(CODE_CHUNKING_FAILED, f"Chunking failed: {detail}", detail=detail)


def no_chunks() -> LibraryMessage:
    return _error(CODE_NO_CHUNKS, "The selected inputs produced no indexable text chunks.")


def cancelled_partial() -> LibraryMessage:
    return _warn(CODE_CANCELLED_PARTIAL, "Indexing was cancelled; partial results were saved.")


def model_unavailable(detail: str) -> LibraryMessage:
    return _error(
        CODE_MODEL_UNAVAILABLE, f"The embedding model is unavailable: {detail}", detail=detail
    )


def embedding_fallback(requested_model: str, local_model: str, detail: str) -> LibraryMessage:
    return _warn(
        CODE_EMBEDDING_FALLBACK,
        f"The selected embedding model could not be used: {detail} "
        f"Falling back to the local offline model ({local_model}).",
        requested_model=requested_model,
        local_model=local_model,
        detail=detail,
    )


def dimension_mismatch(
    requested_dimension: int, model: str, actual_dimension: int
) -> LibraryMessage:
    return _warn(
        CODE_DIMENSION_MISMATCH,
        f"Requested embedding dimension {requested_dimension} is not supported by "
        f"{model!r}; using {actual_dimension}.",
        requested_dimension=requested_dimension,
        model=model,
        actual_dimension=actual_dimension,
    )


def classify_embedding_failure(detail: str) -> LibraryMessage:
    """Return an SSL-specific or generic embedding-failure error from a backend exception."""
    if any(signature in detail.lower() for signature in _SSL_ERROR_SIGNATURES):
        return _error(
            CODE_SSL_CERTIFICATE,
            "Could not reach the embedding service because its TLS/SSL certificate "
            f"could not be verified: {detail}",
            detail=detail,
        )
    return _error(CODE_EMBEDDING_FAILED, f"Embedding or storage failed: {detail}", detail=detail)
