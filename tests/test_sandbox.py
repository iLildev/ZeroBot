"""Tests for the Builder Agent's sandbox manager."""

from pathlib import Path

import pytest

from zerobot.agents.sandbox import (
    DEFAULT_BASH_TIMEOUT,
    SandboxError,
    SandboxManager,
)


@pytest.fixture()
def sandbox(tmp_path: Path) -> SandboxManager:
    """A fresh sandbox manager rooted in a per-test temp directory."""
    return SandboxManager(base_dir=tmp_path)


def test_workspace_is_created_per_user(sandbox: SandboxManager):
    """First call creates the workspace directory; subsequent calls reuse it."""
    ws = sandbox.workspace("alice")
    assert ws.exists()
    assert ws.is_dir()
    assert sandbox.workspace("alice") == ws


def test_invalid_user_id_is_rejected(sandbox: SandboxManager):
    """Slashes and dot prefixes can't be used to escape the base dir."""
    with pytest.raises(SandboxError):
        sandbox.workspace("../evil")
    with pytest.raises(SandboxError):
        sandbox.workspace(".hidden")
    with pytest.raises(SandboxError):
        sandbox.workspace("")


def test_resolve_rejects_absolute_paths(sandbox: SandboxManager):
    """Absolute paths are policy-violations, even if they exist on disk."""
    with pytest.raises(SandboxError):
        sandbox.resolve("alice", "/etc/passwd")
    with pytest.raises(SandboxError):
        sandbox.resolve("alice", "~/secrets")


def test_resolve_rejects_parent_escape(sandbox: SandboxManager):
    """``../`` escapes are caught even when they technically resolve."""
    with pytest.raises(SandboxError):
        sandbox.resolve("alice", "../../etc/passwd")


def test_write_then_read_round_trip(sandbox: SandboxManager):
    """Round-trip a UTF-8 file through ``write_file`` and ``read_file``."""
    n = sandbox.write_file("alice", "notes/hello.txt", "مرحبا")
    assert n > 0
    assert sandbox.read_file("alice", "notes/hello.txt") == "مرحبا"


def test_list_dir_returns_sorted_entries(sandbox: SandboxManager):
    """Directory listings are sorted and report file kinds + sizes."""
    sandbox.write_file("alice", "b.txt", "two")
    sandbox.write_file("alice", "a.txt", "one")
    entries = sandbox.list_dir("alice", ".")
    names = [e["name"] for e in entries]
    assert names == ["a.txt", "b.txt"]
    assert all(e["kind"] == "file" for e in entries)


@pytest.mark.asyncio
async def test_run_bash_captures_output(sandbox: SandboxManager):
    """Bash invocation captures stdout, returns exit code 0."""
    result = await sandbox.run_bash("alice", "echo hello", timeout=DEFAULT_BASH_TIMEOUT)
    assert result.returncode == 0
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_run_bash_rejects_empty(sandbox: SandboxManager):
    """An empty command is a policy error, not an exec attempt."""
    with pytest.raises(SandboxError):
        await sandbox.run_bash("alice", "   ")


@pytest.mark.asyncio
async def test_run_bash_environment_is_minimal(sandbox: SandboxManager):
    """Sensitive host env vars are not forwarded into the subprocess."""
    import os

    # Leak a fake secret into the host env.
    os.environ["BUILDER_TEST_LEAK_KEY"] = "should-not-leak"
    try:
        result = await sandbox.run_bash("alice", "env")
        assert "BUILDER_TEST_LEAK_KEY" not in result.stdout
        assert "should-not-leak" not in result.stdout
    finally:
        os.environ.pop("BUILDER_TEST_LEAK_KEY", None)
