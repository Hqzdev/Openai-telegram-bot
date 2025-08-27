from typing import Dict, Any, List
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta

from app.database.connection import get_db
from app.database.models import User, Plan, Purchase, Usage, Promo
from app.services.billing_service import billing_service
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter()


def require_admin(request: Request) -> int:
    """Require admin authentication"""
    user_id = getattr(request.state, 'user_id', None)
    if not user_id or user_id not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


class UserStats(BaseModel):
    total_users: int
    active_users_today: int
    active_users_week: int
    new_users_today: int
    new_users_week: int


class RevenueStats(BaseModel):
    total_revenue: float
    revenue_today: float
    revenue_week: float
    revenue_month: float


@router.get("/stats/users")
async def get_user_stats(
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Get user statistics"""
    
    # Total users
    total_users = await db.execute(select(func.count(User.id)))
    total_users = total_users.scalar()
    
    # Active users today
    today = datetime.utcnow().date()
    active_today = await db.execute(
        select(func.count(func.distinct(Usage.user_id)))
        .where(func.date(Usage.date) == today)
    )
    active_today = active_today.scalar()
    
    # Active users this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    active_week = await db.execute(
        select(func.count(func.distinct(Usage.user_id)))
        .where(Usage.date >= week_ago)
    )
    active_week = active_week.scalar()
    
    # New users today
    new_today = await db.execute(
        select(func.count(User.id))
        .where(func.date(User.created_at) == today)
    )
    new_today = new_today.scalar()
    
    # New users this week
    new_week = await db.execute(
        select(func.count(User.id))
        .where(User.created_at >= week_ago)
    )
    new_week = new_week.scalar()
    
    return UserStats(
        total_users=total_users,
        active_users_today=active_today,
        active_users_week=active_week,
        new_users_today=new_today,
        new_users_week=new_week
    )


@router.get("/stats/revenue")
async def get_revenue_stats(
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Get revenue statistics"""
    
    # Total revenue
    total_revenue = await db.execute(
        select(func.sum(Purchase.amount))
        .where(Purchase.status == "completed")
    )
    total_revenue = total_revenue.scalar() or 0
    
    # Revenue today
    today = datetime.utcnow().date()
    revenue_today = await db.execute(
        select(func.sum(Purchase.amount))
        .where(
            Purchase.status == "completed",
            func.date(Purchase.completed_at) == today
        )
    )
    revenue_today = revenue_today.scalar() or 0
    
    # Revenue this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    revenue_week = await db.execute(
        select(func.sum(Purchase.amount))
        .where(
            Purchase.status == "completed",
            Purchase.completed_at >= week_ago
        )
    )
    revenue_week = revenue_week.scalar() or 0
    
    # Revenue this month
    month_ago = datetime.utcnow() - timedelta(days=30)
    revenue_month = await db.execute(
        select(func.sum(Purchase.amount))
        .where(
            Purchase.status == "completed",
            Purchase.completed_at >= month_ago
        )
    )
    revenue_month = revenue_month.scalar() or 0
    
    return RevenueStats(
        total_revenue=total_revenue,
        revenue_today=revenue_today,
        revenue_week=revenue_week,
        revenue_month=revenue_month
    )


@router.get("/users")
async def get_users(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Get users list"""
    
    users = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    users = users.scalars().all()
    
    result = []
    for user in users:
        quota = await billing_service.get_user_quota(db, user.id)
        result.append({
            "id": user.id,
            "created_at": user.created_at.isoformat(),
            "lang": user.lang,
            "trial_left": user.trial_left,
            "plan_name": quota.get("plan_name"),
            "plan_until": quota.get("plan_until").isoformat() if quota.get("plan_until") else None,
            "banned": user.banned,
            "remaining_quota": quota.get("remaining")
        })
    
    return {"users": result}


@router.get("/users/{user_id}")
async def get_user_details(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Get user details"""
    
    user = await db.execute(select(User).where(User.id == user_id))
    user = user.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    quota = await billing_service.get_user_quota(db, user.id)
    stats = await billing_service.get_user_stats(db, user.id)
    
    return {
        "id": user.id,
        "created_at": user.created_at.isoformat(),
        "lang": user.lang,
        "trial_left": user.trial_left,
        "plan_name": quota.get("plan_name"),
        "plan_until": quota.get("plan_until").isoformat() if quota.get("plan_until") else None,
        "banned": user.banned,
        "email": user.email,
        "quota": quota,
        "stats": stats
    }


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Ban user"""
    
    user = await db.execute(select(User).where(User.id == user_id))
    user = user.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.banned = True
    await db.commit()
    
    return {"message": "User banned"}


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Unban user"""
    
    user = await db.execute(select(User).where(User.id == user_id))
    user = user.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.banned = False
    await db.commit()
    
    return {"message": "User unbanned"}


@router.post("/users/{user_id}/give-requests")
async def give_requests(
    user_id: int,
    amount: int,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Give trial requests to user"""
    
    success = await billing_service.add_trial_requests(db, user_id, amount)
    
    if success:
        return {"message": f"Added {amount} requests to user {user_id}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to add requests")


@router.get("/plans")
async def get_plans(
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Get all plans"""
    
    plans = await db.execute(select(Plan))
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
            "context_limit": plan.context_limit,
            "is_active": plan.is_active,
            "created_at": plan.created_at.isoformat()
        })
    
    return {"plans": result}


@router.post("/plans")
async def create_plan(
    name: str,
    price_stars: int,
    price_rub: float,
    monthly_quota: int,
    context_limit: int = 8192,
    models_allowed: List[str] = None,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Create new plan"""
    
    if models_allowed is None:
        models_allowed = ["gpt-4o-mini"]
    
    plan = Plan(
        name=name,
        price_stars=price_stars,
        price_rub=price_rub,
        monthly_quota=monthly_quota,
        context_limit=context_limit,
        models_allowed=models_allowed
    )
    
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    return {"message": "Plan created", "plan_id": plan.id}


@router.get("/promos")
async def get_promos(
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Get all promo codes"""
    
    promos = await db.execute(select(Promo))
    promos = promos.scalars().all()
    
    result = []
    for promo in promos:
        result.append({
            "id": promo.id,
            "code": promo.code,
            "discount_percent": promo.discount_percent,
            "discount_fixed": promo.discount_fixed,
            "until": promo.until.isoformat() if promo.until else None,
            "max_uses": promo.max_uses,
            "used": promo.used,
            "is_active": promo.is_active,
            "created_at": promo.created_at.isoformat()
        })
    
    return {"promos": result}


@router.post("/promos")
async def create_promo(
    code: str,
    discount_percent: int = 0,
    discount_fixed: float = 0,
    max_uses: int = 1,
    until: datetime = None,
    db: AsyncSession = Depends(get_db),
    admin_id: int = Depends(require_admin)
):
    """Create new promo code"""
    
    promo = Promo(
        code=code,
        discount_percent=discount_percent,
        discount_fixed=discount_fixed,
        max_uses=max_uses,
        until=until
    )
    
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    
    return {"message": "Promo code created", "promo_id": promo.id}
