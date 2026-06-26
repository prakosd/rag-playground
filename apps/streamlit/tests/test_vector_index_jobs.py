from __future__ import annotations

import time
from pathlib import Path

import pytest
from vector_indexer import IndexingConfig
from vector_indexer.indexer import (
    STAGE_CHUNKING,
    STAGE_EMBEDDING,
    STAGE_LOADING,
    STAGE_RESOLVING_MODEL,
    STAGE_SAVING,
)
from vector_indexer.messages import (
    CODE_EMBEDDING_FAILED,
    CODE_MISSING_AWS_CREDENTIALS,
    CODE_MISSING_OPENAI_KEY,
    CODE_MODEL_UNAVAILABLE,
    CODE_SSL_CERTIFICATE,
)
from vector_indexer.models import IndexingResult

from crawl4md_streamlit import session_manager
from crawl4md_streamlit.vector_index_jobs import (
    drain_events,
    embedding_error_hint_key,
    job_state_from_event,
    request_cancel,
    start_vector_index_job,
    vector_eta_seconds,
    vector_progress_fraction,
    vector_stage_label_key,
)


class _FakeIndexer:
    def __init__(self, result: IndexingResult | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result

    def run(self, config, inputs, output_base, *, progress_callback=None, should_cancel=None):
        self.calls.append({"inputs": list(inputs), "output_base": Path(output_base)})
        if progress_callback is not None:
            progress_callback({"processed_chunks": 1, "total_chunks": 1})
        run_dir = Path(output_base) / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return self._result or IndexingResult(
            success=True,
            output_dir=run_dir,
            indexed_file_count=len(inputs),
            indexed_chunk_count=1,
        )


def _make_session(tmp_path: Path) -> str:
    session_manager.prepare_session_dir(tmp_path, "abc")
    return "abc"


def test_start_vector_index_job_runs_and_emits_events(tmp_path: Path) -> None:
    session_id = _make_session(tmp_path)
    source = tmp_path / "a.md"
    source.write_text("hello", encoding="utf-8")
    fake = _FakeIndexer()

    job = start_vector_index_job(
        session_id=session_id,
        vector_id="01_word",
        config=IndexingConfig(),
        selected_paths=[str(source)],
        uploads=[("notes.txt", b"text")],
        sessions_root=tmp_path,
        indexer=fake,
    )
    job.thread.join(5.0)

    assert not job.thread.is_alive()
    names = [event["event"] for event in drain_events(job)]
    assert "started" in names
    assert "completed" in names
    assert len(fake.calls) == 1
    passed_inputs = fake.calls[0]["inputs"]
    assert any("a.md" in path for path in passed_inputs)
    assert any("notes.txt" in path for path in passed_inputs)
    assert job.output_base == session_manager.vector_output_base(tmp_path, session_id, "01_word")
    assert (job.output_base / "uploads").is_dir()


def test_start_vector_index_job_reports_indexer_failure(tmp_path: Path) -> None:
    session_id = _make_session(tmp_path)

    class _Boom:
        def run(self, *args, **kwargs):
            raise RuntimeError("boom")

    job = start_vector_index_job(
        session_id=session_id,
        vector_id="01_word",
        config=IndexingConfig(),
        selected_paths=[],
        uploads=[("a.md", b"x")],
        sessions_root=tmp_path,
        indexer=_Boom(),
    )
    job.thread.join(5.0)

    failed = [event for event in drain_events(job) if event["event"] == "failed"]
    assert failed
    assert failed[0]["errors"]


def test_request_cancel_sets_event_and_emits(tmp_path: Path) -> None:
    session_id = _make_session(tmp_path)

    class _Waiter:
        def run(self, config, inputs, output_base, *, progress_callback=None, should_cancel=None):
            for _ in range(500):
                if should_cancel is not None and should_cancel():
                    break
                time.sleep(0.01)
            run_dir = Path(output_base) / "run"
            run_dir.mkdir(parents=True, exist_ok=True)
            return IndexingResult(success=False, output_dir=run_dir)

    job = start_vector_index_job(
        session_id=session_id,
        vector_id="01_word",
        config=IndexingConfig(),
        selected_paths=[],
        uploads=[("a.md", b"x")],
        sessions_root=tmp_path,
        indexer=_Waiter(),
    )
    request_cancel(job)
    job.thread.join(5.0)

    assert job.cancel_event.is_set()
    names = [event["event"] for event in drain_events(job)]
    assert "cancel_requested" in names
    assert "cancelled" in names


def test_job_state_from_event_maps_states() -> None:
    assert job_state_from_event("started") == "running"
    assert job_state_from_event("progress") == "running"
    assert job_state_from_event("completed") == "completed"
    assert job_state_from_event("failed") == "failed"
    assert job_state_from_event("cancel_requested") == "cancel_requested"
    assert job_state_from_event("cancelled") == "cancelled"
    assert job_state_from_event("unknown") == "running"


def test_vector_progress_fraction_embedding_equals_chunk_ratio() -> None:
    # The bar equals the chunk fraction so it matches the "Indexed X of Y" caption.
    assert vector_progress_fraction(STAGE_EMBEDDING, processed=0, total=10) == (
        0.0,
        "VEC_STATUS_CHUNKS",
    )
    assert vector_progress_fraction(STAGE_EMBEDDING, processed=5, total=10) == (
        0.5,
        "VEC_STATUS_CHUNKS",
    )
    assert vector_progress_fraction(STAGE_EMBEDDING, processed=10, total=10) == (
        1.0,
        "VEC_STATUS_CHUNKS",
    )


def test_vector_progress_fraction_saving_is_full() -> None:
    assert vector_progress_fraction(STAGE_SAVING) == (1.0, "VEC_STAGE_SAVING")


def test_vector_progress_fraction_indeterminate_stages_return_none() -> None:
    # Pre-embedding stages and embedding-before-counts have no meaningful bar.
    assert vector_progress_fraction(STAGE_RESOLVING_MODEL) is None
    assert vector_progress_fraction(STAGE_LOADING) is None
    assert vector_progress_fraction(STAGE_CHUNKING) is None
    assert vector_progress_fraction(STAGE_EMBEDDING, processed=0, total=0) is None


def test_vector_progress_fraction_unknown_stage_is_none() -> None:
    assert vector_progress_fraction("") is None
    assert vector_progress_fraction("bogus-stage") is None


def test_vector_stage_label_key_maps_known_stages_and_falls_back() -> None:
    assert vector_stage_label_key(STAGE_LOADING) == "VEC_STAGE_LOADING"
    assert vector_stage_label_key(STAGE_EMBEDDING) == "VEC_STAGE_EMBEDDING"
    assert vector_stage_label_key("") == "VEC_STATUS_RUNNING"
    assert vector_stage_label_key("bogus") == "VEC_STATUS_RUNNING"


def test_vector_eta_seconds_estimates_remaining_time() -> None:
    # 2 of 10 chunks took 4s -> 2 chunks/s -> 8 remaining -> ~16s left.
    assert vector_eta_seconds(2, 10, 4.0) == pytest.approx(16.0)


def test_vector_eta_seconds_returns_none_without_enough_signal() -> None:
    assert vector_eta_seconds(0, 10, 5.0) is None  # nothing processed yet
    assert vector_eta_seconds(10, 10, 5.0) is None  # already complete
    assert vector_eta_seconds(3, 0, 5.0) is None  # unknown total
    assert vector_eta_seconds(3, 10, 0.0) is None  # no elapsed time


def test_embedding_error_hint_key_maps_each_cause() -> None:
    assert embedding_error_hint_key([{"code": CODE_SSL_CERTIFICATE}]) == "VEC_ERROR_SSL_HINT"
    assert (
        embedding_error_hint_key([{"code": CODE_MISSING_OPENAI_KEY}]) == "VEC_ERROR_OPENAI_KEY_HINT"
    )
    assert (
        embedding_error_hint_key([{"code": CODE_MISSING_AWS_CREDENTIALS}])
        == "VEC_ERROR_AWS_CREDENTIALS_HINT"
    )
    assert (
        embedding_error_hint_key([{"code": CODE_EMBEDDING_FAILED}])
        == "VEC_ERROR_EMBEDDING_FAILED_HINT"
    )
    assert (
        embedding_error_hint_key([{"code": CODE_MODEL_UNAVAILABLE}])
        == "VEC_ERROR_MODEL_UNAVAILABLE_HINT"
    )


def test_embedding_error_hint_key_prefers_most_specific_cause() -> None:
    errors = [{"code": CODE_MODEL_UNAVAILABLE}, {"code": CODE_SSL_CERTIFICATE}]
    assert embedding_error_hint_key(errors) == "VEC_ERROR_SSL_HINT"


def test_embedding_error_hint_key_returns_none_when_no_hint() -> None:
    assert embedding_error_hint_key([{"code": "vector.no_readable_content"}]) is None
    assert embedding_error_hint_key([]) is None


def test_next_vector_sequence_increments(tmp_path: Path) -> None:
    session_id = _make_session(tmp_path)

    assert session_manager.next_vector_sequence(tmp_path, session_id) == 1
    session_manager.prepare_vector_output_base(tmp_path, session_id, "01_alpha")
    assert session_manager.next_vector_sequence(tmp_path, session_id) == 2


def test_generate_vector_id_and_output_base(tmp_path: Path) -> None:
    session_id = _make_session(tmp_path)

    vector_id = session_manager.generate_vector_id(seq=2)
    assert vector_id.startswith("02_")

    base = session_manager.vector_output_base(tmp_path, session_id, "03_x")
    assert base.name == "vector_03_x"
    assert base.parent.name == "session_abc"
