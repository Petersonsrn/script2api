from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

@router.get("", summary="Health check")
async def health():
    return {"status": "ok", "service": "Script2API"}
