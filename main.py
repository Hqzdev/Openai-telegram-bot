#!/usr/bin/env python3
"""
Telegram AI Assistant - Main Application Entry Point
"""

import asyncio
import uvicorn
from app.api.main import app
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info" if settings.debug else "warning"
    )
