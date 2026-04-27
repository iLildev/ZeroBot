"""Static checks against the smart-defaults planted-bot template.

We don't *import* the template (it imports its sibling ``arcana_helpers``
by relative module name, which only resolves once the bot is planted into
its own venv) — instead we parse it as Python AST and verify the shape
of its handlers, helpers and webhook wiring.
"""

from __future__ import annotations

import ast
from pathlib import Path

TEMPLATE_DIR = Path("arcana/templates/base_template")
MAIN_PY = TEMPLATE_DIR / "main.py"
HELPERS_PY = TEMPLATE_DIR / "arcana_helpers.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_template_files_exist() -> None:
    assert MAIN_PY.is_file()
    assert HELPERS_PY.is_file()


def test_template_main_is_valid_python() -> None:
    _parse(MAIN_PY)  # raises SyntaxError otherwise


def test_template_helpers_is_valid_python() -> None:
    _parse(HELPERS_PY)


def _async_funcs(tree: ast.Module) -> set[str]:
    return {n.name for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}


def test_template_defines_expected_handlers() -> None:
    fns = _async_funcs(_parse(MAIN_PY))
    # Three Telegram command handlers, one callback handler, one webhook.
    assert {"cmd_start", "cmd_help", "cmd_info", "on_button", "handle_webhook"} <= fns


def test_template_imports_helper_module() -> None:
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "from arcana_helpers import register_subscriber, track_event" in src


def test_template_handles_referral_payload() -> None:
    src = MAIN_PY.read_text(encoding="utf-8")
    # Ref payload format: /start ref_<id>
    assert "ref_" in src
    # Must reach register_subscriber with the ref kwarg.
    assert "register_subscriber(BOT_ID" in src
    assert "ref=" in src


def test_helpers_export_two_functions() -> None:
    fns = _async_funcs(_parse(HELPERS_PY))
    assert {"register_subscriber", "track_event"} <= fns


def test_helpers_use_x_bot_token_header() -> None:
    src = HELPERS_PY.read_text(encoding="utf-8")
    assert "X-Bot-Token" in src
    assert "ARCANA_PLATFORM_URL" in src
