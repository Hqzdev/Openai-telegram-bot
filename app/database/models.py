from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, 
    ForeignKey, Float, JSON, BigInteger
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    lang = Column(String(10), default="ru")
    trial_left = Column(Integer, default=30)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    plan_until = Column(DateTime, nullable=True)
    banned = Column(Boolean, default=False)
    email = Column(String(255), nullable=True)
    settings = Column(JSON, default=dict)
    
    # Relationships
    dialogs = relationship("Dialog", back_populates="user")
    purchases = relationship("Purchase", back_populates="user")
    usage = relationship("Usage", back_populates="user")
    plan = relationship("Plan", back_populates="users")


class Dialog(Base):
    __tablename__ = "dialogs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_pinned = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="dialogs")
    messages = relationship("Message", back_populates="dialog", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    dialog_id = Column(Integer, ForeignKey("dialogs.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String(50), nullable=True)
    
    # Relationships
    dialog = relationship("Dialog", back_populates="messages")


class Plan(Base):
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    price_stars = Column(Integer, default=0)
    price_rub = Column(Float, default=0.0)
    monthly_quota = Column(Integer, nullable=False)
    models_allowed = Column(JSON, default=list)
    context_limit = Column(Integer, default=8192)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    users = relationship("User", back_populates="plan")
    purchases = relationship("Purchase", back_populates="plan")


class Purchase(Base):
    __tablename__ = "purchases"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    via = Column(String(20), nullable=False)  # stars, yoomoney
    status = Column(String(20), default="pending")  # pending, completed, failed, refunded
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="purchases")
    plan = relationship("Plan", back_populates="purchases")


class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    provider = Column(String(20), nullable=False)  # yoomoney, stars
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="RUB")
    status = Column(String(20), default="pending")
    ext_id = Column(String(255), nullable=True)  # External payment ID
    ext_payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Usage(Base):
    __tablename__ = "usage"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    requests = Column(Integer, default=0)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", back_populates="usage")


class Promo(Base):
    __tablename__ = "promo"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)
    discount_percent = Column(Integer, default=0)
    discount_fixed = Column(Float, default=0.0)
    until = Column(DateTime, nullable=True)
    max_uses = Column(Integer, default=1)
    used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    role = Column(String(50), default="admin")  # admin, moderator
    created_at = Column(DateTime, default=datetime.utcnow)
    permissions = Column(JSON, default=dict)
