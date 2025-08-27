from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.database.connection import get_db
from app.services.payment_service import payment_service
from app.api.middleware import require_auth
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter()


class YooKassaWebhookRequest(BaseModel):
    type: str
    event: str
    object: Dict[str, Any]


@router.get("/plans")
async def get_plans(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Get available plans"""
    plans = await payment_service.get_plans(db)
    return {"plans": plans}


@router.get("/pricing")
async def get_pricing():
    """Get pricing information"""
    stars_pricing = payment_service.get_stars_pricing()
    return {"stars_pricing": stars_pricing}


@router.post("/yoomoney/webhook")
async def yoomoney_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle YooKassa webhook"""
    
    # Get signature from headers
    signature = request.headers.get("X-YooKassa-Signature")
    if not signature:
        logger.error("Missing YooKassa signature")
        raise HTTPException(status_code=400, detail="Missing signature")
    
    # Get webhook data
    try:
        webhook_data = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook data", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Process webhook
    success = await payment_service.process_yoomoney_webhook(
        db, webhook_data, signature
    )
    
    if success:
        return {"status": "ok"}
    else:
        raise HTTPException(status_code=400, detail="Webhook processing failed")


@router.get("/history")
async def get_payment_history(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Get user's payment history"""
    history = await payment_service.get_payment_history(db, user_id)
    return {"history": history}


@router.post("/create-yoomoney")
async def create_yoomoney_payment(
    plan_name: str,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Create YooKassa payment"""
    
    # Get plan details
    plans = {
        "Start": {"rub": 299, "quota": 300},
        "Pro": {"rub": 799, "quota": 1500},
        "Business": {"rub": 1999, "quota": -1},
        "Pack100": {"rub": 99, "quota": 100},
        "Pack500": {"rub": 399, "quota": 500}
    }
    
    plan = plans.get(plan_name)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    try:
        payment = payment_service.create_yoomoney_payment(
            user_id=user_id,
            plan_name=plan_name,
            amount=plan['rub'],
            description=f"Подписка {plan_name} - {plan['quota'] if plan['quota'] > 0 else 'безлимит'} запросов"
        )
        
        return {
            "payment_id": payment['id'],
            "amount": payment['amount'],
            "currency": payment['currency'],
            "confirmation_url": payment['confirmation_url']
        }
        
    except Exception as e:
        logger.error("Failed to create YooKassa payment", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to create payment"
        )
