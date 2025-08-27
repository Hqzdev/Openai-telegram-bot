import json
from typing import Dict, List, Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    # Telegram Bot
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    app_base_url: str = Field(..., env="APP_BASE_URL")
    
    # OpenAI
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_default_model: str = Field("gpt-4o-mini", env="OPENAI_DEFAULT_MODEL")
    
    # Database
    db_url: str = Field(..., env="DB_URL")
    redis_url: str = Field(..., env="REDIS_URL")
    
    # Monitoring
    sentry_dsn: Optional[str] = Field(None, env="SENTRY_DSN")
    
    # Telegram Stars Pricing
    stars_pricing_json: str = Field(..., env="STARS_PRICING_JSON")
    
    # YooKassa
    yoomoney_shop_id: str = Field(..., env="YOOMONEY_SHOP_ID")
    yoomoney_secret_key: str = Field(..., env="YOOMONEY_SECRET_KEY")
    yoomoney_return_url: str = Field(..., env="YOOMONEY_RETURN_URL")
    yoomoney_webhook_secret: str = Field(..., env="YOOMONEY_WEBHOOK_SECRET")
    
    # Limits & Settings
    trial_requests: int = Field(30, env="TRIAL_REQUESTS")
    requests_per_minute: int = Field(20, env="REQUESTS_PER_MINUTE")
    max_active_jobs_per_user: int = Field(1, env="MAX_ACTIVE_JOBS_PER_USER")
    max_context_tokens: int = Field(8192, env="MAX_CONTEXT_TOKENS")
    stream_timeout: int = Field(40, env="STREAM_TIMEOUT")
    
    # Admin
    admin_user_ids: str = Field("", env="ADMIN_USER_IDS")
    
    # Security
    secret_key: str = Field(..., env="SECRET_KEY")
    webhook_secret: str = Field(..., env="WEBHOOK_SECRET")
    
    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    debug: bool = Field(False, env="DEBUG")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def stars_pricing(self) -> Dict[str, int]:
        """Parse stars pricing from JSON string"""
        try:
            return json.loads(self.stars_pricing_json)
        except (json.JSONDecodeError, TypeError):
            return {
                "trial": 0,
                "start_month": 1000,
                "pro_month": 2500,
                "pack100": 300,
                "pack500": 1200
            }
    
    @property
    def admin_ids(self) -> List[int]:
        """Parse admin user IDs from comma-separated string"""
        if not self.admin_user_ids:
            return []
        return [int(uid.strip()) for uid in self.admin_user_ids.split(",") if uid.strip()]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"


# Global settings instance
settings = Settings()
