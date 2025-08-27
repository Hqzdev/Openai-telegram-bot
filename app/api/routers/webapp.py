from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()

# Templates directory
templates = Jinja2Templates(directory="app/templates")


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat WebApp page"""
    return templates.TemplateResponse("chat.html", {"request": request})


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """History WebApp page"""
    return templates.TemplateResponse("history.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings WebApp page"""
    return templates.TemplateResponse("settings.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin WebApp page"""
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/pay/thanks", response_class=HTMLResponse)
async def payment_thanks_page(request: Request):
    """Payment success page"""
    return templates.TemplateResponse("payment_thanks.html", {"request": request})
