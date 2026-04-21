"""
app/services/stripe_service.py — Regras de negócio de pagamentos e assinaturas.
"""
import stripe
from app.core.config import settings
from app.db import get_user_by_id, get_user_by_stripe_id, update_user_stripe_id, set_user_plan

# Configuração global da biblioteca
stripe.api_key = settings.stripe_api_key

async def create_checkout_session(user_id: int) -> str:
    """Gera uma sessão de checkout e retorna a URL do portal de pagamento do Stripe."""
    user = await get_user_by_id(user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    if user.plan == "pro":
        raise ValueError("Usuário já possui o plano Pro.")

    session_kwargs = {
        "payment_method_types": ["card"],
        "line_items": [{"price": settings.stripe_pro_price_id, "quantity": 1}],
        "mode": "subscription",
        "success_url": settings.origins_list[0] + "/?success=true&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": settings.origins_list[0] + "/?canceled=true",
        "client_reference_id": user_id,
        "metadata": {"user_id": user_id},
    }

    # Anexar cliente existente se houver
    if user.stripe_customer_id:
        session_kwargs["customer"] = user.stripe_customer_id
    else:
        session_kwargs["customer_email"] = user.email

    try:
        session = stripe.checkout.Session.create(**session_kwargs)
        return session.url
    except stripe.StripeError as e:
        raise RuntimeError(f"Erro Stripe ao criar sessão: {str(e)}")

async def create_portal_session(user_id: int) -> str:
    """Gera o link para o usuário gerenciar cartões e assinaturas ativas."""
    user = await get_user_by_id(user_id)
    if not user or not user.stripe_customer_id:
        raise ValueError("Usuário não possui uma assinatura ativa ou perfil no Stripe.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=settings.origins_list[0],
        )
        return session.url
    except stripe.StripeError as e:
        raise RuntimeError(f"Erro Stripe ao acessar portal: {str(e)}")

async def process_webhook(payload: bytes, sig_header: str):
    """Processa eventos assíncronos da Stripe e atualiza a base de dados em tempo real."""
    if not sig_header:
        raise ValueError("Cabeçalho stripe-signature ausente.")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError:
        raise ValueError("Payload inválido.")
    except stripe.error.SignatureVerificationError:
        raise ValueError("Assinatura do webhook inválida.")

    # 1. Checkout Concluído (Primeiro pagamento)
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
        customer_id = session.get("customer")
        
        if user_id and customer_id:
            await update_user_stripe_id(user_id, customer_id)
            await set_user_plan(user_id, "pro")

    # 2. Assinatura Deletada / Cancelada por falta de pagamento ou usuário
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription.get("customer")
        
        if customer_id:
            user = await get_user_by_stripe_id(customer_id)
            if user:
                await set_user_plan(user.id, "free")

    return True
