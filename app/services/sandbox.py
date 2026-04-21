"""
app/services/sandbox.py — Motor de execução segura para scripts enviados pelo usuário.

Camadas de segurança:
  1. AST Audit     — rejeita imports/calls proibidos antes de executar qualquer coisa
  2. Safe Builtins — exec() roda com __builtins__ reduzido (sem open, __import__, etc.)
  3. Timeout       — execução via ThreadPoolExecutor com deadline configurável
  4. Serialização  — resultado validado como JSON-serializable antes de retornar

AVISO: Este sandbox é adequado para demos e desenvolvimento.
       Para produção com usuários externos use isolamento em processo/container (Docker, gVisor).
"""

import ast
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any


# ─────────────────────────────────────────────
#  1. CONSTANTES DE SEGURANÇA
# ─────────────────────────────────────────────

# Módulos banidos — qualquer import desses lança SecurityError
BLOCKED_MODULES: frozenset[str] = frozenset({
    "os", "sys", "subprocess", "socket", "shutil", "ctypes",
    "importlib", "pathlib", "pickle", "marshal", "shelve",
    "multiprocessing", "threading", "signal", "tempfile",
    "builtins", "gc", "resource", "pty", "tty", "atexit",
    "sysconfig", "_thread", "code", "codeop", "compileall",
    "dis", "tokenize", "token", "linecache", "traceback",
})

# Funções/attributes perigosos que não podem aparecer como nomes
BLOCKED_NAMES: frozenset[str] = frozenset({
    "__import__", "__builtins__", "__loader__", "__spec__",
    "exec", "eval", "compile", "open", "globals", "locals",
    "vars", "breakpoint", "memoryview", "bytearray",
    "__class__", "__subclasses__", "__bases__",
})

# Builtins permitidos — apenas operações matemáticas/lógicas seguras
import builtins as _builtins_module

_SAFE_NAMES: tuple[str, ...] = (
    "abs", "all", "any", "bin", "bool", "chr", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hash",
    "hex", "int", "isinstance", "issubclass", "iter", "len", "list",
    "map", "max", "min", "next", "oct", "ord", "pow", "print",
    "range", "repr", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "type", "zip",
    "object", "property", "staticmethod", "classmethod",
    "NotImplemented", "Ellipsis",
    # Exceções seguras
    "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration", "Exception",
    "ArithmeticError", "ZeroDivisionError", "OverflowError",
    "True", "False", "None",
)

SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(_builtins_module, name)
    for name in _SAFE_NAMES
    if hasattr(_builtins_module, name)
}



# ─────────────────────────────────────────────
#  2. ERRO CUSTOMIZADO
# ─────────────────────────────────────────────

class SecurityError(Exception):
    """Lançado quando o script viola as regras de segurança."""


class SandboxTimeoutError(Exception):
    """Lançado quando a execução ultrapassa o timeout."""


# ─────────────────────────────────────────────
#  3. AUDITORIA AST
# ─────────────────────────────────────────────

def audit_ast(source: str) -> None:
    """
    Percorre a AST do script e levanta SecurityError se encontrar:
    - Import de módulos proibidos
    - Uso de atributos/nomes proibidos
    - Chamadas a dunder methods perigosos
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError(f"SyntaxError no script: {e}") from e

    for node in ast.walk(tree):

        # import os / import subprocess
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    raise SecurityError(f"Import proibido: '{alias.name}'")

        # from os import path / from subprocess import run
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module in BLOCKED_MODULES:
                raise SecurityError(f"Import proibido: 'from {node.module} import ...'")

        # Chamadas como eval(...) / exec(...) / __import__(...)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_NAMES:
                raise SecurityError(f"Chamada proibida: '{node.func.id}()'")
            # obj.__class__.__subclasses__() e similares
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_NAMES:
                raise SecurityError(f"Atributo proibido: '.{node.func.attr}'")

        # Acesso a atributos perigosos: obj.__builtins__
        elif isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_NAMES:
                raise SecurityError(f"Atributo proibido: '.{node.attr}'")

        # Uso direto de nomes proibidos como variáveis
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES:
                raise SecurityError(f"Nome proibido: '{node.id}'")


# ─────────────────────────────────────────────
#  4. NAMESPACE SEGURO
# ─────────────────────────────────────────────

def build_safe_globals() -> dict:
    """Retorna um namespace global com apenas builtins seguros."""
    return {"__builtins__": SAFE_BUILTINS}


# ─────────────────────────────────────────────
#  5. SERIALIZAÇÃO SEGURA
# ─────────────────────────────────────────────

def _serialize_result(result: Any) -> Any:
    """Tenta serializar o resultado para JSON. Converte para str se não conseguir."""
    try:
        json.dumps(result)
        return result
    except (TypeError, ValueError):
        return str(result)


# ─────────────────────────────────────────────
#  6. MOTOR DE EXECUÇÃO
# ─────────────────────────────────────────────

def execute_function(
    source: str,
    func_name: str,
    kwargs: dict | None = None,
    timeout: float = 5.0,
) -> dict:
    """
    Pipeline completo de execução segura:
      1. Audita a AST
      2. Executa o source em namespace restrito
      3. Chama a função com kwargs + timeout
      4. Serializa e retorna o resultado

    Returns:
        dict com chaves: success, result, error, exec_time_ms
    """
    kwargs = kwargs or {}
    t_start = time.perf_counter()

    # Etapa 1 — Auditoria AST
    try:
        audit_ast(source)
    except SecurityError as e:
        return {"success": False, "result": None, "error": f"[SecurityError] {e}", "exec_time_ms": 0.0}
    except ValueError as e:
        return {"success": False, "result": None, "error": str(e), "exec_time_ms": 0.0}

    # Etapa 2 — Executar o source em namespace isolado
    safe_globals = build_safe_globals()
    try:
        exec(compile(source, "<sandbox>", "exec"), safe_globals)  # noqa: S102
    except Exception as e:
        return {"success": False, "result": None, "error": f"[ExecError] {type(e).__name__}: {e}", "exec_time_ms": 0.0}

    # Etapa 3 — Recuperar e chamar a função
    fn = safe_globals.get(func_name)
    if fn is None or not callable(fn):
        available = [k for k, v in safe_globals.items() if callable(v) and not k.startswith("_")]
        return {
            "success": False,
            "result": None,
            "error": f"Função '{func_name}' não encontrada. Disponíveis: {available}",
            "exec_time_ms": 0.0,
        }

    def _call():
        return fn(**kwargs)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call)
            raw_result = future.result(timeout=timeout)
    except FuturesTimeoutError:
        exec_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return {
            "success": False,
            "result": None,
            "error": f"[TimeoutError] Execução ultrapassou {timeout}s",
            "exec_time_ms": exec_ms,
        }
    except Exception as e:
        exec_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return {
            "success": False,
            "result": None,
            "error": f"[RuntimeError] {type(e).__name__}: {e}",
            "exec_time_ms": exec_ms,
        }

    # Etapa 4 — Serializar resultado
    exec_ms = round((time.perf_counter() - t_start) * 1000, 2)
    safe_result = _serialize_result(raw_result)

    return {
        "success": True,
        "result": safe_result,
        "error": "",
        "exec_time_ms": exec_ms,
    }
