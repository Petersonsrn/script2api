"""
app/routers/stripe.py — Rotas HTTP para assinaturas e conexão web via o service pattern.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from app.services.auth import get_current_user
from app.services import stripe_service

router = APIRouter(prefix="/billing", tags=["stripe"])

@router.post("/create-checkout-session", summary="Cria sessão de checkout para assinatura Pro")
async def create_checkout_session(current_user: dict = Depends(get_current_user)):
    """Inicia o fluxo hospedado pela Stripe para o usuário assinar o plano Pro."""
    user_id = current_user["sub"]
    try:
        url = await stripe_service.create_checkout_session(user_id)
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-portal-session", summary="Portal de autoatendimento do cliente")
async def create_portal_session(current_user: dict = Depends(get_current_user)):
    """Gera um link para o portal onde o usuário gerencia a assinatura."""
    user_id = current_user["sub"]
    try:
        url = await stripe_service.create_portal_session(user_id)
        return {"url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook", summary="Webhook chamado silenciosamente pela Stripe")
async def stripe_webhook(request: Request):
    """Escuta eventos do Stripe para atualizar o banco de dados via webhook."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        await stripe_service.process_webhook(payload, sig_header)
        return Response(status_code=200)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Webhook Error")
