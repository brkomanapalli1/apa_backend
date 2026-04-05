from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.services.billing_service import BillingService

router = APIRouter()


@router.post('/checkout-session')
def create_checkout_session(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return BillingService(db).create_checkout_session(current_user)


@router.post('/portal-session')
def create_portal_session(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return BillingService(db).create_portal_session(current_user)


@router.post('/webhook')
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias='Stripe-Signature'), db: Session = Depends(get_db)):
    payload = await request.body()
    return BillingService(db).handle_webhook(payload, stripe_signature)
