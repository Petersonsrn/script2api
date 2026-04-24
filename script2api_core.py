"""
script2api_core.py — Transforma qualquer script Python em uma API FastAPI.

Uso:
    python script2api_core.py meu_script.py
    python script2api_core.py meu_script.py --port 9000

Ou importe a função e use programaticamente:
    from script2api_core import script_to_api
    app = script_to_api(source_code)
"""

import ast
import inspect
import sys
import textwrap
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, create_model
from typing import Any


# ─────────────────────────────────────────────
#  1. EXTRAIR FUNÇÕES DO SCRIPT
# ─────────────────────────────────────────────

def extract_functions(source: str) -> list[str]:
    """Retorna os nomes de todas as funções públicas de nível raiz."""
    tree = ast.parse(source)
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.col_offset == 0          # apenas top-level
        and not node.name.startswith("_") # ignorar privadas
    ]


# ─────────────────────────────────────────────
#  2. CRIAR A API DINAMICAMENTE
# ─────────────────────────────────────────────

def script_to_api(source: str, title: str = "Script2API") -> FastAPI:
    """
    Recebe código-fonte Python como string e retorna
    um app FastAPI com um endpoint POST para cada função pública.

    Exemplo:
        source = '''
        def soma(a: int, b: int) -> int:
            return a + b
        '''
        app = script_to_api(source)
    """
    # Executa o script num namespace isolado
    namespace: dict = {}
    exec(compile(source, "<script>", "exec"), namespace)

    # Descobre as funções públicas
    func_names = extract_functions(source)
    if not func_names:
        raise ValueError("Nenhuma função pública encontrada no script.")

    app = FastAPI(
        title=title,
        description=f"API gerada automaticamente para: {', '.join(func_names)}.\n\n🚀 **API gerada em segundos com [Script2API](https://script2api.onrender.com)**",
        version="1.0.0",
    )

    # Cria um endpoint para cada função
    for name in func_names:
        fn = namespace.get(name)
        if not callable(fn):
            continue

        _register_endpoint(app, name, fn)

    return app


# ─────────────────────────────────────────────
#  3. REGISTRAR UM ENDPOINT PARA UMA FUNÇÃO
# ─────────────────────────────────────────────

def _register_endpoint(app: FastAPI, name: str, fn: callable) -> None:
    """Cria dinamicamente um modelo Pydantic e uma rota POST para `fn`."""
    sig = inspect.signature(fn)
    doc = inspect.getdoc(fn) or name

    # Monta os fields do Pydantic a partir dos parâmetros
    fields: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else Any
        default    = param.default    if param.default    != inspect.Parameter.empty else ...
        fields[param_name] = (annotation, default)

    # Cria modelo de entrada dinâmico: ex. SomaInput
    InputModel = create_model(f"{name.capitalize()}Input", **fields)

    # Closure para capturar fn e name corretamente em cada iteração
    def make_endpoint(func, model_class):
        async def endpoint(body: model_class):
            kwargs = body.model_dump()
            result = func(**kwargs)
            return {"function": func.__name__, "result": result}
        endpoint.__name__ = f"endpoint_{func.__name__}"
        endpoint.__doc__  = doc
        return endpoint

    route_handler = make_endpoint(fn, InputModel)

    app.post(
        f"/{name}",
        summary=f"Executa `{name}()`",
        description=doc,
        tags=[name],
    )(route_handler)


# ─────────────────────────────────────────────
#  4. ENTRYPOINT — rode via CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Transforma um script .py em API FastAPI")
    parser.add_argument("script", help="Caminho do arquivo .py")
    parser.add_argument("--port", type=int, default=8000, help="Porta do servidor (padrão: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (padrão: 127.0.0.1)")
    args = parser.parse_args()

    with open(args.script, "r", encoding="utf-8") as f:
        source = f.read()

    title = args.script.replace(".py", "").replace("_", " ").title()
    app   = script_to_api(source, title=title)

    print(f"\n🚀  Script2API rodando!")
    print(f"📄  Script:  {args.script}")
    print(f"🌐  Docs:    http://{args.host}:{args.port}/docs\n")

    uvicorn.run(app, host=args.host, port=args.port)
