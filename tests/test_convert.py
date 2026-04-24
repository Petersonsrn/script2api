"""
tests/test_convert.py — Testes dos endpoints de conversão e execução.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_convert_simple_script(client):
    res = await client.post("/convert", json={
        "source": "def add(a, b):\n    return a + b",
        "script_name": "math",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["script_name"] == "math"
    assert any(e["path"] == "/math/add" for e in body["endpoints"])
    assert "generated_code" in body


@pytest.mark.asyncio
async def test_convert_syntax_error(client):
    res = await client.post("/convert", json={
        "source": "def broken(\n    syntax error",
        "script_name": "bad",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert "SyntaxError" in body["error"]


@pytest.mark.asyncio
async def test_convert_upload_wrong_extension(client):
    from io import BytesIO
    res = await client.post(
        "/convert/upload",
        files={"file": ("readme.txt", BytesIO(b"hello"), "text/plain")},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_run_simple_function(client):
    res = await client.post("/convert/run", json={
        "source": "def greet(name):\n    return f'Hello {name}!'",
        "func_name": "greet",
        "args": {"name": "World"},
    })
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["result"] == "Hello World!"
    assert "exec_time_ms" in body


@pytest.mark.asyncio
async def test_run_function_not_found(client):
    res = await client.post("/convert/run", json={
        "source": "def add(a, b):\n    return a + b",
        "func_name": "sub",
        "args": {},
    })
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_run_security_blocked_import(client):
    res = await client.post("/convert/run", json={
        "source": "import os\ndef evil():\n    return os.getcwd()",
        "func_name": "evil",
        "args": {},
    })
    assert res.status_code == 400
    body = res.json()
    assert "SecurityError" in body["detail"] or "Import proibido" in body["detail"]


@pytest.mark.asyncio
async def test_usage_anonymous(client):
    res = await client.get("/convert/usage")
    assert res.status_code == 200
    body = res.json()
    assert body["plan"] == "free"
    assert "used" in body
    assert "remaining" in body
