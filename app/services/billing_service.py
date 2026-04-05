from __future__ import annotations

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User


class BillingService:
    def __init__(self, db: Session):
        self.db = db
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def _ensure_customer(self, user: User) -> str:
        if not settings.STRIPE_SECRET_KEY:
            raise HTTPException(status_code=400, detail='Stripe is not configured')
        if user.stripe_customer_id:
            return user.stripe_customer_id
        customer = stripe.Customer.create(email=user.email, name=user.full_name)
        user.stripe_customer_id = customer['id']
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return customer['id']

    def create_checkout_session(self, user: User) -> dict:
        if not settings.STRIPE_PRICE_ID:
            raise HTTPException(status_code=400, detail='Stripe price is not configured')
        customer_id = self._ensure_customer(user)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode='subscription',
            line_items=[{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
            success_url=f'{settings.FRONTEND_URL}/billing/success',
            cancel_url=f'{settings.FRONTEND_URL}/billing/cancel',
            allow_promotion_codes=True,
        )
        return {'url': session.url}

    def create_portal_session(self, user: User) -> dict:
        customer_id = self._ensure_customer(user)
        portal = stripe.billing_portal.Session.create(customer=customer_id, return_url=settings.FRONTEND_URL)
        return {'url': portal.url}

    def handle_webhook(self, payload: bytes, signature: str | None) -> dict:
        if not settings.STRIPE_WEBHOOK_SECRET:
            return {'received': True, 'mode': 'dev'}
        try:
            event = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        event_type = event['type']
        data = event['data']['object']
        if event_type in {'customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'}:
            customer_id = data.get('customer')
            status = data.get('status', 'free')
            user = self.db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if user:
                user.subscription_status = status
                self.db.add(user)
                self.db.commit()
        return {'received': True, 'type': event_type}
