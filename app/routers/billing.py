"""
app/routers/billing.py — Integração completa com Stripe.

Endpoints:
  POST /billing/create-checkout-session — Inicia checkout de assinatura Pro
  POST /billing/create-portal-session  — Abre Customer Portal Stripe
  POST /billing/webhook                — Recebe e processa eventos Stripe (idempotente)

Eventos suportados:
  - checkout.session.completed         → ativa plano Pro
  - customer.subscription.updated      → sincroniza status
  - customer.subscription.deleted      → downgrade para free
  - invoice.paid                       → confirma renovação
  - invoice.payment_failed             → notifica falha (log)
"""
from __future__ import annotations

import json
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import settings
from app.db import (
    get_user_by_id,
    get_user_by_stripe_id,
    update_user_stripe_id,
    set_user_plan,
    upsert_subscription,
    save_webhook_event,
    is_event_processed,
    mark_event_processed,
)
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_api_key

router = APIRouter(prefix="/billing", tags=["billing"])


# ─────────────────────────────────────────────
#  CHECKOUT SESSION
# ─────────────────────────────────────────────

@router.post("/create-checkout-session", summary="Cria sessão de checkout para assinatura Pro")
async def create_checkout_session(current_user: dict = Depends(get_current_user)):
    """Inicia fluxo hospedado no Stripe para o usuário assinar o plano Pro."""
    user_id = current_user["sub"]
    user = await get_user_by_id(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.plan == "pro":
        raise HTTPException(status_code=400, detail="Usuário já possui o plano Pro.")

    try:
        session_kwargs: dict = {
            "payment_method_types": ["card"],
            "line_items": [{"price": settings.stripe_pro_price_id, "quantity": 1}],
            "mode": "subscription",
            "success_url": settings.frontend_url + "/?success=true&session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": settings.frontend_url + "/?canceled=true",
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
        logger.error("Stripe error on checkout: %s", e)
        raise HTTPException(status_code=502, detail=f"Erro ao criar sessão de pagamento: {e.user_message or str(e)}")


# ─────────────────────────────────────────────
#  CUSTOMER PORTAL
# ─────────────────────────────────────────────

@router.post("/create-portal-session", summary="Portal de autoatendimento do cliente")
async def create_portal_session(current_user: dict = Depends(get_current_user)):
    """Gera link para o portal do Stripe onde o usuário gerencia assinatura e cartões."""
    user_id = current_user["sub"]
    user = await get_user_by_id(user_id)

    if not user or not user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="Usuário ainda não possui assinatura ativa para gerenciar.",
        )

    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=settings.frontend_url,
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        logger.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=502, detail=f"Erro ao acessar portal: {e.user_message or str(e)}")


# ─────────────────────────────────────────────
#  WEBHOOK — idempotente, completo
# ─────────────────────────────────────────────

@router.post("/webhook", summary="Webhook do Stripe — recebe eventos de assinatura")
async def stripe_webhook(request: Request):
    """
    Processa eventos do Stripe de forma idempotente.
    - Verifica assinatura HMAC antes de qualquer operação.
    - Salva payload bruto para auditoria.
    - Ignora silenciosamente eventos já processados.
    """
    payload_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # ── 1. Verificação de assinatura ─────────────────
    try:
        event = stripe.Webhook.construct_event(
            payload_bytes, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        logger.warning("Webhook: payload inválido.")
        raise HTTPException(status_code=400, detail="Payload inválido.")
    except stripe.SignatureVerificationError:
        logger.warning("Webhook: assinatura inválida.")
        raise HTTPException(status_code=400, detail="Assinatura inválida.")

    event_id: str = event["id"]
    event_type: str = event["type"]

    # ── 2. Idempotência ───────────────────────────────
    if await is_event_processed(event_id):
        logger.info("Webhook %s já processado — ignorando.", event_id)
        return Response(status_code=200)

    # Salva payload bruto para auditoria (antes de processar)
    await save_webhook_event(
        event_id=event_id,
        event_type=event_type,
        payload=payload_bytes.decode("utf-8"),
        processed=False,
    )

    # ── 3. Roteamento de eventos ──────────────────────
    try:
        await _handle_event(event_type, event["data"]["object"])
    except Exception as exc:
        logger.exception("Erro ao processar webhook %s (%s): %s", event_id, event_type, exc)
        # Retorna 200 mesmo com erro para o Stripe não reenviar indefinidamente.
        # O payload salvo permite reprocessar manualmente.
        return Response(status_code=200)

    # ── 4. Marca como processado ──────────────────────
    await mark_event_processed(event_id)
    logger.info("Webhook %s [%s] processado com sucesso.", event_id, event_type)
    return Response(status_code=200)


async def _handle_event(event_type: str, obj: dict) -> None:
    """Despacha o evento Stripe para o handler correto."""

    match event_type:

        # ✅ Checkout concluído — primeiro pagamento ou reativação
        case "checkout.session.completed":
            user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id")
            customer_id = obj.get("customer")
            subscription_id = obj.get("subscription")

            if not user_id:
                logger.warning("checkout.session.completed sem user_id — ignorado.")
                return

            if customer_id:
                await update_user_stripe_id(user_id, customer_id)

            await set_user_plan(user_id, "pro")

            if subscription_id:
                await upsert_subscription(
                    user_id=user_id,
                    stripe_subscription_id=subscription_id,
                    status="active",
                )
            logger.info("Usuário %s ativado como Pro.", user_id)

        # 🔄 Assinatura atualizada (ex.: troca de plano, renovação agendada)
        case "customer.subscription.updated":
            subscription_id = obj.get("id")
            customer_id = obj.get("customer")
            status = obj.get("status", "active")
            period_end = obj.get("current_period_end")
            period_end_str = str(period_end) if period_end else None

            if customer_id:
                user = await get_user_by_stripe_id(customer_id)
                if user and subscription_id:
                    await upsert_subscription(
                        user_id=user.id,
                        stripe_subscription_id=subscription_id,
                        status=status,
                        current_period_end=period_end_str,
                    )

        # ❌ Assinatura cancelada (pelo usuário ou por falha de pagamento)
        case "customer.subscription.deleted":
            customer_id = obj.get("customer")
            subscription_id = obj.get("id")

            if customer_id:
                user = await get_user_by_stripe_id(customer_id)
                if user:
                    await set_user_plan(user.id, "free")
                    if subscription_id:
                        await upsert_subscription(
                            user_id=user.id,
                            stripe_subscription_id=subscription_id,
                            status="canceled",
                        )
                    logger.info("Usuário %s revertido para free.", user.id)

        # 💰 Fatura paga — confirma renovação mensal
        case "invoice.paid":
            customer_id = obj.get("customer")
            subscription_id = obj.get("subscription")

            if customer_id:
                user = await get_user_by_stripe_id(customer_id)
                if user:
                    # Garante que o plano está como Pro após renovação
                    if user.plan != "pro":
                        await set_user_plan(user.id, "pro")
                    logger.info("Fatura paga para usuário %s.", user.id)

        # ⚠️ Falha de pagamento — notifica mas não downgrade imediato
        case "invoice.payment_failed":
            customer_id = obj.get("customer")
            attempt_count = obj.get("attempt_count", 1)
            logger.warning(
                "Falha de pagamento (tentativa %s) para customer %s.",
                attempt_count, customer_id,
            )
            # O downgrade real ocorre via customer.subscription.deleted
            # quando o Stripe encerrar a assinatura após N tentativas.

        # Evento não mapeado — apenas loga
        case _:
            logger.debug("Evento Stripe não mapeado: %s", event_type)
