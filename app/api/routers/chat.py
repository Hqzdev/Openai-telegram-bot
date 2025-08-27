from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import asyncio

from app.database.connection import get_db
from app.database.models import User, Dialog, Message as DBMessage
from app.services.openai_service import openai_service
from app.services.billing_service import billing_service
from app.api.middleware import require_auth
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    dialog_id: Optional[int] = None
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    dialog_id: int
    message_id: int
    tokens_used: int


@router.get("/quota")
async def get_user_quota(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Get user's current quota"""
    quota = await billing_service.get_user_quota(db, user_id)
    return {"quota": quota}


@router.post("/send")
async def send_message(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Send message and get AI response"""
    
    # Check if user can make request
    can_request = await billing_service.can_make_request(db, user_id)
    if not can_request:
        raise HTTPException(
            status_code=402, 
            detail="Insufficient quota. Please upgrade your plan."
        )
    
    # Get or create dialog
    if request.dialog_id:
        dialog = await db.execute(
            select(Dialog).where(
                Dialog.id == request.dialog_id,
                Dialog.user_id == user_id
            )
        )
        dialog = dialog.scalar_one_or_none()
        if not dialog:
            raise HTTPException(status_code=404, detail="Dialog not found")
    else:
        # Create new dialog
        dialog = Dialog(
            user_id=user_id,
            title=await openai_service.generate_dialog_title(request.message)
        )
        db.add(dialog)
        await db.commit()
        await db.refresh(dialog)
    
    # Save user message
    user_message = DBMessage(
        dialog_id=dialog.id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    
    # Get conversation history
    messages = await db.execute(
        select(DBMessage).where(DBMessage.dialog_id == dialog.id)
        .order_by(DBMessage.created_at)
    )
    messages = messages.scalars().all()
    
    # Convert to OpenAI format
    openai_messages = []
    for msg in messages:
        openai_messages.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # Truncate messages if needed
    max_tokens = 8192  # Default context limit
    openai_messages = openai_service.truncate_messages(
        openai_messages, max_tokens, request.model
    )
    
    # Consume request quota
    success = await billing_service.consume_request(db, user_id)
    if not success:
        raise HTTPException(
            status_code=402,
            detail="Failed to consume quota"
        )
    
    # Generate AI response
    try:
        response_content = ""
        async for chunk in openai_service.chat_completion(
            messages=openai_messages,
            model=request.model,
            temperature=request.temperature,
            system_prompt=request.system_prompt
        ):
            response_content += chunk
        
        # Save AI response
        ai_message = DBMessage(
            dialog_id=dialog.id,
            role="assistant",
            content=response_content,
            model_used=request.model or openai_service.default_model
        )
        db.add(ai_message)
        await db.commit()
        await db.refresh(ai_message)
        
        # Update dialog timestamp
        dialog.updated_at = ai_message.created_at
        await db.commit()
        
        return ChatResponse(
            response=response_content,
            dialog_id=dialog.id,
            message_id=ai_message.id,
            tokens_used=openai_service.count_tokens(response_content)
        )
        
    except Exception as e:
        logger.error("Failed to generate AI response", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate response"
        )


@router.post("/stream")
async def stream_message(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Stream AI response"""
    
    # Check if user can make request
    can_request = await billing_service.can_make_request(db, user_id)
    if not can_request:
        raise HTTPException(
            status_code=402, 
            detail="Insufficient quota. Please upgrade your plan."
        )
    
    # Get or create dialog
    if request.dialog_id:
        dialog = await db.execute(
            select(Dialog).where(
                Dialog.id == request.dialog_id,
                Dialog.user_id == user_id
            )
        )
        dialog = dialog.scalar_one_or_none()
        if not dialog:
            raise HTTPException(status_code=404, detail="Dialog not found")
    else:
        # Create new dialog
        dialog = Dialog(
            user_id=user_id,
            title=await openai_service.generate_dialog_title(request.message)
        )
        db.add(dialog)
        await db.commit()
        await db.refresh(dialog)
    
    # Save user message
    user_message = DBMessage(
        dialog_id=dialog.id,
        role="user",
        content=request.message
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    
    # Get conversation history
    messages = await db.execute(
        select(DBMessage).where(DBMessage.dialog_id == dialog.id)
        .order_by(DBMessage.created_at)
    )
    messages = messages.scalars().all()
    
    # Convert to OpenAI format
    openai_messages = []
    for msg in messages:
        openai_messages.append({
            "role": msg.role,
            "content": msg.content
        })
    
    # Truncate messages if needed
    max_tokens = 8192  # Default context limit
    openai_messages = openai_service.truncate_messages(
        openai_messages, max_tokens, request.model
    )
    
    # Consume request quota
    success = await billing_service.consume_request(db, user_id)
    if not success:
        raise HTTPException(
            status_code=402,
            detail="Failed to consume quota"
        )
    
    async def generate_stream():
        """Generate streaming response"""
        response_content = ""
        
        try:
            async for chunk in openai_service.chat_completion(
                messages=openai_messages,
                model=request.model,
                temperature=request.temperature,
                system_prompt=request.system_prompt
            ):
                response_content += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            # Save complete AI response
            ai_message = DBMessage(
                dialog_id=dialog.id,
                role="assistant",
                content=response_content,
                model_used=request.model or openai_service.default_model
            )
            db.add(ai_message)
            await db.commit()
            
            # Update dialog timestamp
            dialog.updated_at = ai_message.created_at
            await db.commit()
            
            # Send completion signal
            yield f"data: {json.dumps({'done': True, 'dialog_id': dialog.id, 'message_id': ai_message.id})}\n\n"
            
        except Exception as e:
            logger.error("Failed to generate streaming response", error=str(e), user_id=user_id)
            yield f"data: {json.dumps({'error': 'Failed to generate response'})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )


@router.get("/dialogs")
async def get_dialogs(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Get user's dialogs"""
    dialogs = await db.execute(
        select(Dialog).where(Dialog.user_id == user_id)
        .order_by(Dialog.updated_at.desc())
    )
    dialogs = dialogs.scalars().all()
    
    result = []
    for dialog in dialogs:
        result.append({
            "id": dialog.id,
            "title": dialog.title,
            "created_at": dialog.created_at.isoformat(),
            "updated_at": dialog.updated_at.isoformat(),
            "is_pinned": dialog.is_pinned
        })
    
    return {"dialogs": result}


@router.get("/dialogs/{dialog_id}/messages")
async def get_dialog_messages(
    dialog_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Get messages from specific dialog"""
    
    # Check if dialog belongs to user
    dialog = await db.execute(
        select(Dialog).where(
            Dialog.id == dialog_id,
            Dialog.user_id == user_id
        )
    )
    dialog = dialog.scalar_one_or_none()
    
    if not dialog:
        raise HTTPException(status_code=404, detail="Dialog not found")
    
    messages = await db.execute(
        select(DBMessage).where(DBMessage.dialog_id == dialog_id)
        .order_by(DBMessage.created_at)
    )
    messages = messages.scalars().all()
    
    result = []
    for message in messages:
        result.append({
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "model_used": message.model_used
        })
    
    return {"messages": result}


@router.delete("/dialogs/{dialog_id}")
async def delete_dialog(
    dialog_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Delete dialog"""
    
    # Check if dialog belongs to user
    dialog = await db.execute(
        select(Dialog).where(
            Dialog.id == dialog_id,
            Dialog.user_id == user_id
        )
    )
    dialog = dialog.scalar_one_or_none()
    
    if not dialog:
        raise HTTPException(status_code=404, detail="Dialog not found")
    
    await db.delete(dialog)
    await db.commit()
    
    return {"message": "Dialog deleted"}


@router.post("/dialogs/{dialog_id}/pin")
async def pin_dialog(
    dialog_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(require_auth)
):
    """Pin/unpin dialog"""
    
    # Check if dialog belongs to user
    dialog = await db.execute(
        select(Dialog).where(
            Dialog.id == dialog_id,
            Dialog.user_id == user_id
        )
    )
    dialog = dialog.scalar_one_or_none()
    
    if not dialog:
        raise HTTPException(status_code=404, detail="Dialog not found")
    
    dialog.is_pinned = not dialog.is_pinned
    await db.commit()
    
    return {"pinned": dialog.is_pinned}
