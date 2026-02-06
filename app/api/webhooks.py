"""Webhook endpoints for payment providers and Telegram."""
import logging
from fastapi import APIRouter, Request, HTTPException
from app.db.session import AsyncSessionLocal
from app.services.payment_service import PaymentService, YooKassaService
from app.services.subscription_service import SubscriptionService
from app.services.sharing_service import SharingService
from app.models.payment import PaymentStatus, PaymentType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/yookassa")
async def yookassa_webhook(request: Request):
    """Handle YooKassa payment notifications."""
    try:
        body = await request.json()
        event_type = body.get("event")
        payment_data = body.get("object", {})
        provider_payment_id = payment_data.get("id")

        if not provider_payment_id:
            raise HTTPException(status_code=400, detail="Missing payment ID")

        async with AsyncSessionLocal() as session:
            payment_service = PaymentService(session)
            payment = await payment_service.get_payment_by_provider_id(provider_payment_id)

            if not payment:
                logger.warning(f"YooKassa webhook: payment {provider_payment_id} not found")
                return {"status": "ok"}

            if event_type == "payment.succeeded":
                await payment_service.update_payment_status(
                    payment.id,
                    PaymentStatus.SUCCEEDED.value,
                    provider_data=payment_data,
                )

                # Handle subscription activation
                if payment.payment_type == PaymentType.SUBSCRIPTION.value and payment.subscription_id:
                    sub_service = SubscriptionService(session)
                    await sub_service.renew_subscription(payment.subscription_id)
                    logger.info(f"Subscription {payment.subscription_id} activated via YooKassa")

                # Handle contact purchase
                elif payment.payment_type == PaymentType.CONTACT_PURCHASE.value and payment.contact_share_id:
                    sharing_service = SharingService(session)
                    share = await sharing_service.get_share_by_id(payment.contact_share_id)
                    if share:
                        await sharing_service.purchase_contact(
                            share_id=share.id,
                            buyer_id=payment.user_id,
                            payment_id=payment.id,
                            amount_paid=str(payment.amount),
                            currency=payment.currency,
                        )
                        logger.info(f"Contact purchase completed via YooKassa for share {share.id}")

            elif event_type == "payment.canceled":
                await payment_service.update_payment_status(
                    payment.id,
                    PaymentStatus.CANCELLED.value,
                    provider_data=payment_data,
                )

            elif event_type == "refund.succeeded":
                await payment_service.update_payment_status(
                    payment.id,
                    PaymentStatus.REFUNDED.value,
                    provider_data=payment_data,
                )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"YooKassa webhook error: {e}")
        return {"status": "error"}
