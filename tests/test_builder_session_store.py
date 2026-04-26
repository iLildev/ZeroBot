"""Tests for the on-disk Builder Agent session store."""

import json
from pathlib import Path

from zerobot.agents.builder_agent import Session, SessionStore


def test_get_creates_empty_session_for_new_user(tmp_path: Path):
    """First access mints a fresh session."""
    store = SessionStore(tmp_path)
    s = store.get("alice")
    assert isinstance(s, Session)
    assert s.user_id == "alice"
    assert s.messages == []
    assert s.total_input_tokens == 0


def test_save_then_reload_round_trip(tmp_path: Path):
    """A saved session is reloaded with all fields intact across instances."""
    store = SessionStore(tmp_path)
    s = store.get("alice")
    s.messages.append({"role": "user", "content": "hi"})
    s.total_input_tokens = 12
    s.total_output_tokens = 7
    store.save("alice")

    fresh = SessionStore(tmp_path)
    loaded = fresh.get("alice")
    assert loaded.messages == [{"role": "user", "content": "hi"}]
    assert loaded.total_input_tokens == 12
    assert loaded.total_output_tokens == 7


def test_reset_clears_disk(tmp_path: Path):
    """``reset`` wipes both the cache and the on-disk file."""
    store = SessionStore(tmp_path)
    store.get("alice").messages.append({"x": 1})
    store.save("alice")
    assert (tmp_path / "alice" / "session.json").exists()

    store.reset("alice")
    assert not (tmp_path / "alice" / "session.json").exists()


def test_corrupt_file_yields_fresh_session(tmp_path: Path):
    """A bad JSON file logs a warning and falls back to an empty session."""
    user_dir = tmp_path / "alice"
    user_dir.mkdir()
    (user_dir / "session.json").write_text("{not json", encoding="utf-8")

    store = SessionStore(tmp_path)
    s = store.get("alice")
    assert s.messages == []


def test_in_memory_mode_when_base_dir_is_none():
    """``base_dir=None`` keeps everything in memory and never raises."""
    store = SessionStore(base_dir=None)
    s = store.get("bob")
    s.messages.append({"role": "user", "content": "hi"})
    store.save("bob")  # no-op, no exception
    # Still cached.
    assert store.get("bob").messages == [{"role": "user", "content": "hi"}]


def test_invalid_user_id_does_not_touch_disk(tmp_path: Path):
    """User ids with slashes / dot prefix are kept memory-only."""
    store = SessionStore(tmp_path)
    s = store.get("../evil")
    s.messages.append({"x": 1})
    store.save("../evil")
    # Nothing must have escaped to the base dir.
    leaked = list(tmp_path.rglob("session.json"))
    assert leaked == []


def test_save_writes_valid_json(tmp_path: Path):
    """The on-disk file is valid JSON with the expected keys."""
    store = SessionStore(tmp_path)
    store.get("alice").messages.append({"role": "user", "content": "hi"})
    store.save("alice")

    raw = (tmp_path / "alice" / "session.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["user_id"] == "alice"
    assert data["messages"] == [{"role": "user", "content": "hi"}]
