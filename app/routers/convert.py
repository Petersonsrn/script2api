"""
app/routers/convert.py — Endpoints de conversao e execucao de scripts.

Rate-limit mensal por usuario + historico persistente via SQLite.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db import log_upload
from app.services.converter import convert
from app.services.sandbox import execute_function
from app.services.auth import get_current_user_optional
from app.services.usage import check_rate_limit, build_usage

router = APIRouter(prefix="/convert", tags=["convert"])


# ─────────────────────────────────────────────
#  SCHEMAS
# ─────────────────────────────────────────────

class ConvertRequest(BaseModel):
    source: str
    script_name: str = "script"

class ConvertResponse(BaseModel):
    success: bool
    script_name: str = ""
    endpoints: list[dict] = []
    generated_code: str = ""
    warnings: list[str] = []
    usage: dict = {}
    error: str = ""

class RunRequest(BaseModel):
    source: str = Field(..., description="Codigo-fonte Python completo")
    func_name: str = Field(..., description="Nome da funcao a executar")
    args: dict = Field(default={}, description="Argumentos keyword para a funcao")
    timeout: float = Field(default=5.0, ge=0.1, le=10.0)

class RunResponse(BaseModel):
    success: bool
    func_name: str
    result: Any = None
    error: str = ""
    exec_time_ms: float = 0.0
    security_note: str = "Executed in a restricted sandbox."
    usage: dict = {}


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _guard_source_size(source: str) -> None:
    max_bytes = settings.sandbox_max_source_kb * 1024
    if len(source.encode("utf-8")) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Script muito grande. Maximo: {settings.sandbox_max_source_kb} KB.",
        )

def _clamp_timeout(t: float) -> float:
    return min(t, settings.sandbox_timeout)


# ─────────────────────────────────────────────
#  CONVERSAO — JSON
# ─────────────────────────────────────────────

@router.post("", response_model=ConvertResponse, summary="Convert Python source to API")
async def convert_script(
    req: ConvertRequest,
    current_user: dict = Depends(get_current_user_optional),
):
    """Converte codigo Python enviado como JSON."""
    usage_info = await check_rate_limit(current_user)
    result = convert(req.source, script_name=req.script_name)

    status_val = "success" if result.get("success") else "error"
    await log_upload(
        user_id=usage_info["user_id"],
        filename=f"{req.script_name}.py",
        script_name=req.script_name,
        endpoints_n=len(result.get("endpoints", [])),
        status=status_val,
        error_msg=result.get("error", ""),
    )
    # Re-check used count after logging
    usage_info["used"] += 1
    if usage_info["remaining"] is not None:
        usage_info["remaining"] = max(0, usage_info["remaining"] - 1)

    result["usage"] = usage_info
    return result


# ─────────────────────────────────────────────
#  CONVERSAO — UPLOAD
# ─────────────────────────────────────────────

@router.post("/upload", response_model=ConvertResponse, summary="Upload .py and convert")
async def convert_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_optional),
):
    """Faz upload de um arquivo .py e gera os endpoints correspondentes."""
    if not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Apenas arquivos .py sao aceitos.")

    source = (await file.read()).decode("utf-8", errors="replace")
    _guard_source_size(source)
    usage_info = await check_rate_limit(current_user)

    script_name = file.filename.replace(".py", "").replace(" ", "_").lower()
    result = convert(source, script_name=script_name)

    status_val = "success" if result.get("success") else "error"
    await log_upload(
        user_id=usage_info["user_id"],
        filename=file.filename,
        script_name=script_name,
        endpoints_n=len(result.get("endpoints", [])),
        status=status_val,
        error_msg=result.get("error", ""),
    )
    usage_info["used"] += 1
    if usage_info["remaining"] is not None:
        usage_info["remaining"] = max(0, usage_info["remaining"] - 1)

    result["usage"] = usage_info
    return result


# ─────────────────────────────────────────────
#  EXECUCAO — JSON
# ─────────────────────────────────────────────

@router.post("/run", response_model=RunResponse, summary="Execute a function from Python source")
async def run_function(
    req: RunRequest,
    current_user: dict = Depends(get_current_user_optional),
):
    """Executa uma funcao especifica de um script Python em sandbox seguro."""
    _guard_source_size(req.source)
    usage_info = await check_rate_limit(current_user)
    timeout = _clamp_timeout(req.timeout)

    outcome = execute_function(
        source=req.source,
        func_name=req.func_name,
        kwargs=req.args,
        timeout=timeout,
    )

    status_val = "success" if outcome["success"] else "error"
    await log_upload(
        user_id=usage_info["user_id"],
        filename="<inline>",
        script_name=req.func_name,
        endpoints_n=1 if outcome["success"] else 0,
        status=status_val,
        error_msg=outcome.get("error", ""),
    )
    usage_info["used"] += 1
    if usage_info["remaining"] is not None:
        usage_info["remaining"] = max(0, usage_info["remaining"] - 1)

    if not outcome["success"]:
        err = outcome["error"]
        code = 408 if "TimeoutError" in err else 400 if "SecurityError" in err else 422
        raise HTTPException(status_code=code, detail=err)

    return RunResponse(
        success=True,
        func_name=req.func_name,
        result=outcome["result"],
        exec_time_ms=outcome["exec_time_ms"],
        usage=usage_info,
    )


# ─────────────────────────────────────────────
#  EXECUCAO — UPLOAD
# ─────────────────────────────────────────────

@router.post("/upload-and-run", response_model=RunResponse, summary="Upload .py and run a function")
async def upload_and_run(
    file: UploadFile = File(..., description="Arquivo .py"),
    func_name: str = Form(..., description="Nome da funcao a executar"),
    args: str = Form(default="{}", description='JSON kwargs. Ex: {"a": 1}'),
    timeout: float = Form(default=5.0, ge=0.1, le=10.0),
    current_user: dict = Depends(get_current_user_optional),
):
    """Upload de arquivo .py e execucao direta de uma funcao no sandbox."""
    import json as _json

    if not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Apenas arquivos .py sao aceitos.")

    source = (await file.read()).decode("utf-8", errors="replace")
    _guard_source_size(source)

    try:
        kwargs = _json.loads(args)
        if not isinstance(kwargs, dict):
            raise ValueError()
    except (ValueError, _json.JSONDecodeError) as e:
        raise HTTPException(status_code=422, detail=f"args invalido: {e}")

    usage_info = await check_rate_limit(current_user)
    timeout = _clamp_timeout(timeout)

    outcome = execute_function(source=source, func_name=func_name, kwargs=kwargs, timeout=timeout)

    status_val = "success" if outcome["success"] else "error"
    await log_upload(
        user_id=usage_info["user_id"],
        filename=file.filename,
        script_name=func_name,
        endpoints_n=1 if outcome["success"] else 0,
        status=status_val,
        error_msg=outcome.get("error", ""),
    )
    usage_info["used"] += 1
    if usage_info["remaining"] is not None:
        usage_info["remaining"] = max(0, usage_info["remaining"] - 1)

    if not outcome["success"]:
        err = outcome["error"]
        code = 408 if "TimeoutError" in err else 400 if "SecurityError" in err else 422
        raise HTTPException(status_code=code, detail=err)

    return RunResponse(
        success=True,
        func_name=func_name,
        result=outcome["result"],
        exec_time_ms=outcome["exec_time_ms"],
        usage=usage_info,
    )


# ─────────────────────────────────────────────
#  USAGE CHECK
# ─────────────────────────────────────────────

@router.get("/usage", summary="Verificar uso do usuario atual")
async def get_usage(current_user: dict = Depends(get_current_user_optional)):
    """Retorna o uso mensal do usuario autenticado (ou anonimo)."""
    user_id = current_user.get("sub") or current_user.get("id", "anonymous")
    plan = current_user.get("plan", "free")
    usage = await build_usage(user_id, plan)
    return {"user_id": user_id, **usage}
