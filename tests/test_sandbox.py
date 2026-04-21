"""
tests/test_sandbox.py — Testes do motor de execução segura.
"""
from __future__ import annotations

import pytest
from app.services.sandbox import (
    audit_ast,
    execute_function,
    SecurityError,
)


# ── AST Audit ─────────────────────────────────────────────────────────────────

def test_audit_blocks_os_import():
    with pytest.raises(SecurityError, match="Import proibido"):
        audit_ast("import os")


def test_audit_blocks_subprocess():
    with pytest.raises(SecurityError, match="Import proibido"):
        audit_ast("import subprocess")


def test_audit_blocks_from_os():
    with pytest.raises(SecurityError, match="Import proibido"):
        audit_ast("from os import path")


def test_audit_blocks_eval():
    with pytest.raises(SecurityError, match="Chamada proibida"):
        audit_ast("eval('1+1')")


def test_audit_blocks_exec():
    with pytest.raises(SecurityError, match="Chamada proibida"):
        audit_ast("exec('x = 1')")


def test_audit_allows_safe_code():
    """Código sem imports perigosos deve passar sem exceção."""
    audit_ast("""
def add(a, b):
    return a + b
""")


# ── Execute Function ──────────────────────────────────────────────────────────

def test_execute_simple_function():
    source = "def add(a, b):\n    return a + b"
    result = execute_function(source, "add", {"a": 2, "b": 3})
    assert result["success"] is True
    assert result["result"] == 5


def test_execute_string_return():
    source = "def greet(name):\n    return f'Hello, {name}!'"
    result = execute_function(source, "greet", {"name": "World"})
    assert result["success"] is True
    assert result["result"] == "Hello, World!"


def test_execute_function_not_found():
    source = "def add(a, b):\n    return a + b"
    result = execute_function(source, "nonexistent")
    assert result["success"] is False
    assert "não encontrada" in result["error"]


def test_execute_blocks_os_import():
    source = "import os\ndef evil():\n    return os.getcwd()"
    result = execute_function(source, "evil")
    assert result["success"] is False
    assert "SecurityError" in result["error"] or "Import proibido" in result["error"]


def test_execute_timeout():
    source = "def slow():\n    import time\n    time.sleep(999)"
    # time não está na whitelist do AST — deve falhar antes do timeout
    result = execute_function(source, "slow", timeout=1.0)
    assert result["success"] is False


def test_execute_syntax_error():
    source = "def broken(\n    syntax error"
    result = execute_function(source, "broken")
    assert result["success"] is False
    assert "SyntaxError" in result["error"]


def test_execute_returns_exec_time():
    source = "def noop():\n    return None"
    result = execute_function(source, "noop")
    assert "exec_time_ms" in result
    assert result["exec_time_ms"] >= 0
