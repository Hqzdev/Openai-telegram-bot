from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from app.database.models import User, Plan, Purchase, Usage, Promo
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)


class BillingService:
    def __init__(self):
        self.trial_requests = settings.trial_requests
        
    async def get_user_quota(self, session: AsyncSession, user_id: int) -> Dict[str, Any]:
        """
        Get user's current quota and subscription status
        """
        user = await session.execute(
            select(User).options(selectinload(User.plan)).where(User.id == user_id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            return {
                "trial_left": self.trial_requests,
                "plan_name": None,
                "plan_until": None,
                "monthly_quota": 0,
                "used_this_month": 0,
                "remaining": self.trial_requests,
                "is_trial": True,
                "is_active": True
            }
        
        # Check if user has active plan
        is_active = False
        monthly_quota = 0
        plan_name = None
        
        if user.plan_id and user.plan_until and user.plan_until > datetime.utcnow():
            is_active = True
            plan_name = user.plan.name if user.plan else None
            monthly_quota = user.plan.monthly_quota if user.plan else 0
        
        # Get usage for current month
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        usage_result = await session.execute(
            select(func.sum(Usage.requests)).where(
                and_(
                    Usage.user_id == user_id,
                    Usage.date >= start_of_month
                )
            )
        )
        used_this_month = usage_result.scalar() or 0
        
        # Calculate remaining
        if is_active:
            remaining = max(0, monthly_quota - used_this_month)
        else:
            remaining = max(0, user.trial_left)
        
        return {
            "trial_left": user.trial_left,
            "plan_name": plan_name,
            "plan_until": user.plan_until,
            "monthly_quota": monthly_quota,
            "used_this_month": used_this_month,
            "remaining": remaining,
            "is_trial": not is_active,
            "is_active": is_active
        }
    
    async def can_make_request(self, session: AsyncSession, user_id: int) -> bool:
        """
        Check if user can make a request
        """
        quota = await self.get_user_quota(session, user_id)
        return quota["remaining"] > 0
    
    async def consume_request(self, session: AsyncSession, user_id: int, tokens: int = 1) -> bool:
        """
        Consume one request from user's quota
        """
        user = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            return False
        
        # Check if user has active plan
        if user.plan_id and user.plan_until and user.plan_until > datetime.utcnow():
            # User has active subscription - just log usage
            await self._log_usage(session, user_id, tokens)
            return True
        else:
            # User is on trial
            if user.trial_left > 0:
                user.trial_left -= 1
                await self._log_usage(session, user_id, tokens)
                await session.commit()
                return True
            else:
                return False
    
    async def _log_usage(self, session: AsyncSession, user_id: int, tokens: int):
        """
        Log usage statistics
        """
        today = datetime.utcnow().date()
        
        # Check if usage record exists for today
        usage = await session.execute(
            select(Usage).where(
                and_(
                    Usage.user_id == user_id,
                    func.date(Usage.date) == today
                )
            )
        )
        usage = usage.scalar_one_or_none()
        
        if usage:
            usage.requests += 1
            usage.total_tokens += tokens
        else:
            usage = Usage(
                user_id=user_id,
                requests=1,
                total_tokens=tokens
            )
            session.add(usage)
        
        await session.commit()
    
    async def activate_plan(
        self, 
        session: AsyncSession, 
        user_id: int, 
        plan_id: int, 
        duration_days: int = 30
    ) -> bool:
        """
        Activate plan for user
        """
        user = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            return False
        
        user.plan_id = plan_id
        user.plan_until = datetime.utcnow() + timedelta(days=duration_days)
        
        await session.commit()
        logger.info("Plan activated", user_id=user_id, plan_id=plan_id, duration_days=duration_days)
        return True
    
    async def add_trial_requests(
        self, 
        session: AsyncSession, 
        user_id: int, 
        amount: int
    ) -> bool:
        """
        Add trial requests to user
        """
        user = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            return False
        
        user.trial_left += amount
        await session.commit()
        
        logger.info("Trial requests added", user_id=user_id, amount=amount, new_total=user.trial_left)
        return True
    
    async def get_plans(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """
        Get all active plans
        """
        plans = await session.execute(
            select(Plan).where(Plan.is_active == True)
        )
        plans = plans.scalars().all()
        
        result = []
        for plan in plans:
            result.append({
                "id": plan.id,
                "name": plan.name,
                "price_stars": plan.price_stars,
                "price_rub": plan.price_rub,
                "monthly_quota": plan.monthly_quota,
                "models_allowed": plan.models_allowed,
                "context_limit": plan.context_limit
            })
        
        return result
    
    async def validate_promo(self, session: AsyncSession, code: str) -> Optional[Dict[str, Any]]:
        """
        Validate promo code
        """
        promo = await session.execute(
            select(Promo).where(
                and_(
                    Promo.code == code,
                    Promo.is_active == True
                )
            )
        )
        promo = promo.scalar_one_or_none()
        
        if not promo:
            return None
        
        # Check if promo is expired
        if promo.until and promo.until < datetime.utcnow():
            return None
        
        # Check if promo usage limit exceeded
        if promo.used >= promo.max_uses:
            return None
        
        return {
            "id": promo.id,
            "code": promo.code,
            "discount_percent": promo.discount_percent,
            "discount_fixed": promo.discount_fixed,
            "max_uses": promo.max_uses,
            "used": promo.used
        }
    
    async def apply_promo(self, session: AsyncSession, promo_id: int) -> bool:
        """
        Mark promo code as used
        """
        promo = await session.execute(
            select(Promo).where(Promo.id == promo_id)
        )
        promo = promo.scalar_one_or_none()
        
        if not promo:
            return False
        
        promo.used += 1
        await session.commit()
        return True
    
    async def get_user_stats(self, session: AsyncSession, user_id: int) -> Dict[str, Any]:
        """
        Get user statistics
        """
        # Total requests
        total_requests = await session.execute(
            select(func.sum(Usage.requests)).where(Usage.user_id == user_id)
        )
        total_requests = total_requests.scalar() or 0
        
        # Total tokens
        total_tokens = await session.execute(
            select(func.sum(Usage.total_tokens)).where(Usage.user_id == user_id)
        )
        total_tokens = total_tokens.scalar() or 0
        
        # Purchases count
        purchases_count = await session.execute(
            select(func.count(Purchase.id)).where(
                and_(
                    Purchase.user_id == user_id,
                    Purchase.status == "completed"
                )
            )
        )
        purchases_count = purchases_count.scalar() or 0
        
        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "purchases_count": purchases_count
        }


# Global service instance
billing_service = BillingService()
