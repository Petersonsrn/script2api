"""
app/routers/billing.py — Integração com Stripe para assinaturas SaaS.
"""

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import settings
from app.db import get_user_by_id, get_user_by_stripe_id, update_user_stripe_id, set_user_plan
from app.services.auth import get_current_user

# Configuração da chave de API do Stripe
stripe.api_key = settings.stripe_api_key

router = APIRouter(prefix="/billing", tags=["billing"])


# ─────────────────────────────────────────────
#  CHECKOUT
# ─────────────────────────────────────────────

@router.post("/create-checkout-session", summary="Cria sessao de checkout para assinatura Pro")
async def create_checkout_session(current_user: dict = Depends(get_current_user)):
    """Inicia um fluxo hospedado pela Stripe para o usuário assinar o plano Pro."""
    user_id = current_user["sub"]
    user = await get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    if user.plan == "pro":
        raise HTTPException(status_code=400, detail="Usuario ja possui o plano Pro.")

    try:
        # Se o usuário já tiver um id na Stripe mas o plano expirou, passamos o customer_id
        session_kwargs = {
            "payment_method_types": ["card"],
            "line_items": [{"price": settings.stripe_pro_price_id, "quantity": 1}],
            "mode": "subscription",
            "success_url": settings.origins_list[0] + "/?success=true&session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": settings.origins_list[0] + "/?canceled=true",
            "client_reference_id": user_id,
            "metadata": {"user_id": user_id},
        }

        if user.stripe_customer_id:
            session_kwargs["customer"] = user.stripe_customer_id
        else:
            session_kwargs["customer_email"] = user.email

        session = stripe.checkout.Session.create(**session_kwargs)
        return {"url": session.url}
    except stripe.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro interno ao criar sessao de pagamento.")


# ─────────────────────────────────────────────
#  CUSTOMER PORTAL
# ─────────────────────────────────────────────

@router.post("/create-portal-session", summary="Portal de autoatendimento do cliente")
async def create_portal_session(current_user: dict = Depends(get_current_user)):
    """Gera um link para o portal onde o usuário gerencia a assinatura e cartões."""
    user_id = current_user["sub"]
    user = await get_user_by_id(user_id)

    if not user or not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Usuario nao possui uma assinatura ativa/Stripe ID.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=settings.origins_list[0],
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
#  WEBHOOKS
# ─────────────────────────────────────────────

@router.post("/webhook", summary="Webhook chamado pela Stripe")
async def stripe_webhook(request: Request):
    """Escuta eventos de assinatura do Stripe para atualizar o SQLite de forma assíncrona."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError as e:
        # Payload invalido
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Assinatura invalida
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 1. Checkout Concluído (Primeiro pagamento / Assinatura criada)
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Pega a user_id do metadata
        user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
        customer_id = session.get("customer")
        
        if user_id and customer_id:
            await update_user_stripe_id(user_id, customer_id)
            await set_user_plan(user_id, "pro")

    # 2. Assinatura Deletada / Cancelada por falta de pagamento ou pelo usuario
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get("customer")
        
        if customer_id:
            user = await get_user_by_stripe_id(customer_id)
            if user:
                await set_user_plan(user.id, "free")

    # 3. Fatura paga / Assinatura atualizada (Renovações)
    elif event['type'] in ['invoice.paid', 'customer.subscription.updated']:
        pass


    return Response(status_code=200)
