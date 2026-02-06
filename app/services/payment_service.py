import logging
import uuid
import hashlib
import hmac
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.payment import Payment, PaymentStatus, PaymentType, PaymentProvider
from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_payment(
        self,
        user_id: uuid.UUID,
        payment_type: str,
        provider: str,
        amount: float,
        currency: str = "RUB",
        description: str = None,
        subscription_id: uuid.UUID = None,
        contact_share_id: uuid.UUID = None,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            payment_type=payment_type,
            provider=provider,
            amount=Decimal(str(amount)),
            currency=currency,
            description=description,
            status=PaymentStatus.PENDING.value,
            subscription_id=subscription_id,
            contact_share_id=contact_share_id,
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def update_payment_status(
        self,
        payment_id: uuid.UUID,
        status: str,
        provider_payment_id: str = None,
        provider_data: dict = None,
    ) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        payment = result.scalars().first()
        if not payment:
            return None

        payment.status = status
        if provider_payment_id:
            payment.provider_payment_id = provider_payment_id
        if provider_data:
            payment.provider_data = provider_data

        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_payment(self, payment_id: uuid.UUID) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.id == payment_id)
        )
        return result.scalars().first()

    async def get_payment_by_provider_id(self, provider_payment_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )
        return result.scalars().first()

    async def get_user_payments(self, user_id: uuid.UUID, limit: int = 20) -> list:
        stmt = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class YooKassaService:
    """YooKassa payment integration."""

    def __init__(self):
        self.shop_id = settings.YOOKASSA_SHOP_ID
        self.secret_key = settings.YOOKASSA_SECRET_KEY

    @property
    def is_configured(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    async def create_payment(
        self,
        amount: float,
        currency: str = "RUB",
        description: str = "",
        return_url: str = None,
        metadata: dict = None,
    ) -> Dict[str, Any]:
        """Create a YooKassa payment via API."""
        if not self.is_configured:
            raise ValueError("YooKassa not configured")

        import aiohttp
        import json

        idempotence_key = str(uuid.uuid4())
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency,
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or f"https://{settings.APP_DOMAIN or 'localhost'}/payment/success",
            },
            "capture": True,
            "description": description,
            "metadata": metadata or {},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                auth=aiohttp.BasicAuth(self.shop_id, self.secret_key),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json",
                },
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"YooKassa error: {data}")
                    raise ValueError(f"YooKassa API error: {data.get('description', 'Unknown')}")
                return data

    async def create_recurring_payment(
        self,
        payment_method_id: str,
        amount: float,
        currency: str = "RUB",
        description: str = "",
        metadata: dict = None,
    ) -> Dict[str, Any]:
        """Create a recurring payment using saved payment method."""
        if not self.is_configured:
            raise ValueError("YooKassa not configured")

        import aiohttp

        idempotence_key = str(uuid.uuid4())
        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency,
            },
            "payment_method_id": payment_method_id,
            "capture": True,
            "description": description,
            "metadata": metadata or {},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                auth=aiohttp.BasicAuth(self.shop_id, self.secret_key),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json",
                },
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"YooKassa recurring error: {data}")
                    raise ValueError(f"YooKassa API error: {data.get('description', 'Unknown')}")
                return data

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Verify YooKassa webhook signature."""
        if not self.secret_key:
            return False
        computed = hmac.new(
            self.secret_key.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, signature)


class TelegramPaymentService:
    """Telegram native payments (Stars)."""

    @property
    def is_configured(self) -> bool:
        return bool(settings.TELEGRAM_PAYMENT_PROVIDER_TOKEN)

    def get_provider_token(self) -> str:
        return settings.TELEGRAM_PAYMENT_PROVIDER_TOKEN or ""

    def create_invoice_params(
        self,
        title: str,
        description: str,
        payload: str,
        amount: int,
        currency: str = "XTR",  # Telegram Stars
    ) -> dict:
        """Build params for bot.send_invoice()."""
        return {
            "title": title,
            "description": description,
            "payload": payload,
            "provider_token": self.get_provider_token() if currency != "XTR" else "",
            "currency": currency,
            "prices": [{"label": title, "amount": amount}],
        }
