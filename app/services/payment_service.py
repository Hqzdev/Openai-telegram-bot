import hashlib
import hmac
import json
from datetime import datetime
from typing import Dict, Any, Optional
from yookassa import Payment as YooKassaPayment
from yookassa.domain.request import PaymentRequest
from yookassa.domain.common import Currency
from app.config import settings
from app.database.models import Purchase, Invoice
from app.services.billing_service import billing_service
import structlog

logger = structlog.get_logger(__name__)


class PaymentService:
    def __init__(self):
        self.stars_pricing = settings.stars_pricing
        self.yoomoney_shop_id = settings.yoomoney_shop_id
        self.yoomoney_secret_key = settings.yoomoney_secret_key
        self.yoomoney_return_url = settings.yoomoney_return_url
        self.yoomoney_webhook_secret = settings.yoomoney_webhook_secret
    
    def get_stars_pricing(self) -> Dict[str, int]:
        """
        Get Telegram Stars pricing
        """
        return self.stars_pricing
    
    def create_stars_invoice(
        self, 
        user_id: int, 
        plan_name: str, 
        amount: int
    ) -> Dict[str, Any]:
        """
        Create Telegram Stars invoice
        """
        # Create invoice record
        invoice_data = {
            "user_id": user_id,
            "provider": "stars",
            "amount": amount,
            "currency": "STARS",
            "status": "pending",
            "ext_payload": {
                "plan_name": plan_name,
                "amount_stars": amount
            }
        }
        
        return invoice_data
    
    async def process_stars_payment(
        self, 
        session, 
        user_id: int, 
        plan_name: str, 
        telegram_charge_id: str,
        amount: int
    ) -> bool:
        """
        Process successful Telegram Stars payment
        """
        # Create idempotency key
        idempotency_key = f"stars_{user_id}_{plan_name}_{telegram_charge_id}"
        
        # Check if payment already processed
        existing_purchase = await session.execute(
            f"SELECT id FROM purchases WHERE payload->>'idempotency_key' = '{idempotency_key}'"
        )
        if existing_purchase.scalar_one_or_none():
            logger.info("Stars payment already processed", idempotency_key=idempotency_key)
            return True
        
        # Get plan by name
        plan = await session.execute(
            f"SELECT id FROM plans WHERE name = '{plan_name}'"
        )
        plan = plan.scalar_one_or_none()
        
        if not plan:
            logger.error("Plan not found", plan_name=plan_name)
            return False
        
        # Create purchase record
        purchase = Purchase(
            user_id=user_id,
            plan_id=plan,
            via="stars",
            status="completed",
            amount=amount,
            currency="STARS",
            payload={
                "idempotency_key": idempotency_key,
                "telegram_charge_id": telegram_charge_id,
                "plan_name": plan_name
            },
            completed_at=datetime.utcnow()
        )
        session.add(purchase)
        
        # Activate plan
        success = await billing_service.activate_plan(session, user_id, plan)
        
        if success:
            await session.commit()
            logger.info("Stars payment processed successfully", 
                       user_id=user_id, plan_name=plan_name, amount=amount)
            return True
        else:
            await session.rollback()
            logger.error("Failed to activate plan after Stars payment", 
                        user_id=user_id, plan_name=plan_name)
            return False
    
    def create_yoomoney_payment(
        self, 
        user_id: int, 
        plan_name: str, 
        amount: float,
        description: str
    ) -> Dict[str, Any]:
        """
        Create YooKassa payment
        """
        try:
            payment_request = PaymentRequest(
                amount={
                    "value": str(amount),
                    "currency": Currency.RUB
                },
                confirmation={
                    "type": "redirect",
                    "return_url": self.yoomoney_return_url
                },
                capture=True,
                description=description,
                metadata={
                    "user_id": user_id,
                    "plan_name": plan_name
                }
            )
            
            payment = YooKassaPayment.create(payment_request, idempotence_key=f"yoomoney_{user_id}_{plan_name}_{datetime.utcnow().timestamp()}")
            
            return {
                "id": payment.id,
                "status": payment.status,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "confirmation_url": payment.confirmation.confirmation_url,
                "metadata": payment.metadata
            }
            
        except Exception as e:
            logger.error("Failed to create YooKassa payment", error=str(e))
            raise
    
    async def process_yoomoney_webhook(
        self, 
        session, 
        webhook_data: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Process YooKassa webhook
        """
        # Verify signature
        if not self._verify_yoomoney_signature(webhook_data, signature):
            logger.error("Invalid YooKassa webhook signature")
            return False
        
        payment_id = webhook_data.get("object", {}).get("id")
        status = webhook_data.get("object", {}).get("status")
        metadata = webhook_data.get("object", {}).get("metadata", {})
        
        if not payment_id or status != "succeeded":
            logger.info("YooKassa payment not succeeded", payment_id=payment_id, status=status)
            return False
        
        user_id = metadata.get("user_id")
        plan_name = metadata.get("plan_name")
        
        if not user_id or not plan_name:
            logger.error("Missing metadata in YooKassa payment", payment_id=payment_id)
            return False
        
        # Check if payment already processed
        existing_purchase = await session.execute(
            f"SELECT id FROM purchases WHERE payload->>'yoomoney_payment_id' = '{payment_id}'"
        )
        if existing_purchase.scalar_one_or_none():
            logger.info("YooKassa payment already processed", payment_id=payment_id)
            return True
        
        # Get plan by name
        plan = await session.execute(
            f"SELECT id FROM plans WHERE name = '{plan_name}'"
        )
        plan = plan.scalar_one_or_none()
        
        if not plan:
            logger.error("Plan not found", plan_name=plan_name)
            return False
        
        # Get payment amount
        amount = webhook_data.get("object", {}).get("amount", {}).get("value", 0)
        
        # Create purchase record
        purchase = Purchase(
            user_id=user_id,
            plan_id=plan,
            via="yoomoney",
            status="completed",
            amount=float(amount),
            currency="RUB",
            payload={
                "yoomoney_payment_id": payment_id,
                "plan_name": plan_name,
                "webhook_data": webhook_data
            },
            completed_at=datetime.utcnow()
        )
        session.add(purchase)
        
        # Activate plan
        success = await billing_service.activate_plan(session, user_id, plan)
        
        if success:
            await session.commit()
            logger.info("YooKassa payment processed successfully", 
                       user_id=user_id, plan_name=plan_name, payment_id=payment_id)
            return True
        else:
            await session.rollback()
            logger.error("Failed to activate plan after YooKassa payment", 
                        user_id=user_id, plan_name=plan_name)
            return False
    
    def _verify_yoomoney_signature(self, webhook_data: Dict[str, Any], signature: str) -> bool:
        """
        Verify YooKassa webhook signature
        """
        try:
            # Create signature from webhook data
            data_string = json.dumps(webhook_data, separators=(',', ':'))
            expected_signature = hmac.new(
                self.yoomoney_webhook_secret.encode('utf-8'),
                data_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error("Error verifying YooKassa signature", error=str(e))
            return False
    
    async def get_payment_history(
        self, 
        session, 
        user_id: int, 
        limit: int = 10
    ) -> list:
        """
        Get user's payment history
        """
        purchases = await session.execute(
            f"""
            SELECT p.*, pl.name as plan_name 
            FROM purchases p 
            LEFT JOIN plans pl ON p.plan_id = pl.id 
            WHERE p.user_id = {user_id} 
            ORDER BY p.created_at DESC 
            LIMIT {limit}
            """
        )
        
        result = []
        for row in purchases:
            result.append({
                "id": row.id,
                "plan_name": row.plan_name,
                "via": row.via,
                "status": row.status,
                "amount": row.amount,
                "currency": row.currency,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None
            })
        
        return result


# Global service instance
payment_service = PaymentService()
