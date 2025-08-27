import time
import json
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)


async def auth_middleware(request: Request, call_next):
    """Authentication and logging middleware"""
    start_time = time.time()
    
    # Extract user info from Telegram WebApp init data
    user_id = None
    try:
        init_data = request.query_params.get("tgWebAppData")
        if init_data:
            # Parse Telegram WebApp init data
            # In production, you should verify the signature
            import urllib.parse
            parsed_data = dict(urllib.parse.parse_qsl(init_data))
            user_id = parsed_data.get("user", {}).get("id")
    except Exception as e:
        logger.warning("Failed to parse Telegram WebApp data", error=str(e))
    
    # Add user_id to request state
    request.state.user_id = user_id
    
    # Process request
    try:
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log request
        logger.info(
            "Request processed",
            method=request.method,
            url=str(request.url),
            status_code=response.status_code,
            process_time=process_time,
            user_id=user_id
        )
        
        # Add processing time header
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
        
    except Exception as e:
        # Log error
        logger.error(
            "Request failed",
            method=request.method,
            url=str(request.url),
            error=str(e),
            user_id=user_id
        )
        
        # Return error response
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )


def get_current_user_id(request: Request) -> Optional[int]:
    """Get current user ID from request state"""
    return getattr(request.state, 'user_id', None)


def require_auth(request: Request) -> int:
    """Require authentication and return user ID"""
    user_id = get_current_user_id(request)
    if not user_id:
        raise ValueError("Authentication required")
    return int(user_id)
