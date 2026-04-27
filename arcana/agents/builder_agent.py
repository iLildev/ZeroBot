"""The Builder Agent loop.

Given a user message, the agent calls Claude with the registered tools,
executes any tool calls Claude requests, feeds the results back, and
repeats until Claude stops requesting tools (``stop_reason == "end_turn"``)
or the iteration cap is hit.

Sessions are persisted as a JSON file per user under
``BUILDER_SESSION_DIR/{user_id}/session.json`` so that conversations
survive restarts. The store falls back to in-memory mode if the directory
is unwritable, which keeps unit tests and ephemeral environments working.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from arcana.agents.llm import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, get_client
from arcana.agents.sandbox import SandboxManager
from arcana.agents.tools import TOOL_SCHEMAS, execute_tool

log = logging.getLogger(__name__)

# Safety cap on tool-use loops per user turn.
MAX_ITERATIONS = 30

SYSTEM_PROMPT = """You are Builder Agent, an autonomous coding assistant running inside the Arcana platform.

Capabilities:
- You operate inside a sandboxed Linux workspace. All paths are relative to the workspace root.
- You can run bash commands, read/write files, list directories, and fetch URLs.
- Use git, pip, npm, curl, and standard Unix tools as needed.

Working style:
- Plan before acting on non-trivial tasks. Briefly state the plan, then execute step-by-step.
- Prefer small, verifiable steps. After each significant change, run a check (tests, linter, smoke run).
- Keep replies concise — the user reads them in a chat client. Use markdown code blocks for code.
- When the user writes in Arabic, reply in Arabic. Otherwise mirror their language.
- Surface errors honestly. Never claim success without verification.
- Never attempt to leave the sandbox or read host environment variables that are not part of your toolset.
"""


# ── session memory ─────────────────────────────────────────────────────────


@dataclass
class Session:
    """Per-user conversation state, persisted across restarts when possible."""

    user_id: str
    messages: list[dict] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class SessionStore:
    """Disk-backed session store with an in-memory cache.

    Each session is serialized as ``{base_dir}/{user_id}/session.json``.
    If *base_dir* is ``None`` (or unwritable), the store degrades to
    process-local memory only — useful for tests and ephemeral runs.
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._cache: dict[str, Session] = {}
        self._base_dir: Path | None = None
        if base_dir is not None:
            try:
                self._base_dir = Path(base_dir)
                self._base_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.warning("SessionStore: disabling disk persistence (%s)", exc)
                self._base_dir = None

    # ── helpers ────────────────────────────────────────────────────────────

    def _path_for(self, user_id: str) -> Path | None:
        if self._base_dir is None:
            return None
        if not user_id or "/" in user_id or user_id.startswith("."):
            return None
        return self._base_dir / user_id / "session.json"

    def _load(self, user_id: str) -> Session | None:
        path = self._path_for(user_id)
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Session(
                user_id=data.get("user_id", user_id),
                messages=list(data.get("messages", [])),
                total_input_tokens=int(data.get("total_input_tokens", 0)),
                total_output_tokens=int(data.get("total_output_tokens", 0)),
            )
        except (OSError, ValueError) as exc:
            log.warning("SessionStore: failed to load %s (%s); starting fresh", path, exc)
            return None

    def _save(self, session: Session) -> None:
        path = self._path_for(session.user_id)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(asdict(session), ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            log.warning("SessionStore: failed to save %s (%s)", path, exc)

    # ── public API ─────────────────────────────────────────────────────────

    def get(self, user_id: str) -> Session:
        """Return (loading from disk on first access) the session for *user_id*."""
        if user_id not in self._cache:
            loaded = self._load(user_id)
            self._cache[user_id] = loaded or Session(user_id=user_id)
        return self._cache[user_id]

    def save(self, user_id: str) -> None:
        """Flush the cached session for *user_id* to disk."""
        if user_id in self._cache:
            self._save(self._cache[user_id])

    def reset(self, user_id: str) -> None:
        """Forget *user_id*'s session entirely (cache + disk)."""
        self._cache.pop(user_id, None)
        path = self._path_for(user_id)
        if path is not None and path.exists():
            with contextlib.suppress(OSError):
                path.unlink()


# ── agent loop ─────────────────────────────────────────────────────────────


@dataclass
class TurnResult:
    """Aggregate metrics + final assistant text returned by ``run_turn``."""

    reply: str
    iterations: int
    tool_calls: int
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        """Sum of input and output tokens for the whole turn."""
        return self.input_tokens + self.output_tokens


# A coroutine called by the agent with intermediate progress strings (text or
# tool labels). The Telegram bot uses it to live-edit a placeholder reply.
ProgressCallback = Callable[[str], Awaitable[None]]


class BuilderAgent:
    """High-level orchestration of one Claude turn + its tool calls."""

    def __init__(
        self,
        sandbox: SandboxManager | None = None,
        sessions: SessionStore | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.sandbox = sandbox or SandboxManager()
        if sessions is None:
            # Default: persist sessions next to the sandbox workspaces.
            sessions = SessionStore(self.sandbox.base_dir)
        self.sessions = sessions
        self.model = model
        self.max_tokens = max_tokens
        self._client = get_client()

    async def run_turn(
        self,
        user_id: str,
        user_message: str,
        on_progress: ProgressCallback | None = None,
    ) -> TurnResult:
        """Process a single user message and return the assistant's final reply."""
        session = self.sessions.get(user_id)
        session.messages.append({"role": "user", "content": user_message})

        iterations = 0
        tool_calls = 0
        input_tokens = 0
        output_tokens = 0
        final_text = ""

        try:
            while iterations < MAX_ITERATIONS:
                iterations += 1
                response = await self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_SCHEMAS,
                    messages=session.messages,
                )
                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens

                # Always record the assistant turn (text + tool_use blocks) so the
                # next iteration can reference tool_use ids.
                session.messages.append(
                    {
                        "role": "assistant",
                        "content": [_block_to_dict(b) for b in response.content],
                    }
                )

                # Collect text + tool_use blocks from this turn.
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                text_blocks = [b.text for b in response.content if b.type == "text"]
                current_text = "\n".join(t for t in text_blocks if t).strip()
                if current_text:
                    final_text = current_text
                    if on_progress:
                        try:
                            await on_progress(current_text)
                        except Exception:  # noqa: BLE001
                            log.exception("progress callback failed")

                if response.stop_reason != "tool_use" or not tool_uses:
                    break

                # Execute every tool call requested in this turn, in order.
                results = []
                for tu in tool_uses:
                    tool_calls += 1
                    if on_progress:
                        with contextlib.suppress(Exception):
                            await on_progress(f"⚙️ {tu.name}({_brief(tu.input)})")
                    output = await execute_tool(user_id, tu.name, dict(tu.input), self.sandbox)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": output,
                        }
                    )
                session.messages.append({"role": "user", "content": results})
        finally:
            session.total_input_tokens += input_tokens
            session.total_output_tokens += output_tokens
            # Persist whatever progress we have, even if the turn errored.
            self.sessions.save(user_id)

        if not final_text:
            final_text = "(no reply)"

        return TurnResult(
            reply=final_text,
            iterations=iterations,
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def reset(self, user_id: str) -> None:
        """Forget a user's history and wipe their workspace."""
        self.sessions.reset(user_id)
        self.sandbox.reset_workspace(user_id)


# ── helpers ────────────────────────────────────────────────────────────────


def _block_to_dict(block) -> dict:
    """Convert an Anthropic content block into the plain dict shape required.

    The Anthropic SDK returns rich objects for response blocks, but the
    request format expects them echoed back as plain dicts.
    """
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": dict(block.input),
        }
    # Future-proof: pass anything else through ``model_dump`` if available.
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return {"type": block.type}


def _brief(payload: dict, limit: int = 60) -> str:
    """Render a compact one-line preview of tool inputs for progress messages."""
    try:
        items = []
        for k, v in payload.items():
            sv = str(v).replace("\n", " ")
            if len(sv) > limit:
                sv = sv[: limit - 1] + "…"
            items.append(f"{k}={sv}")
        return ", ".join(items)
    except Exception:  # noqa: BLE001
        return "..."
