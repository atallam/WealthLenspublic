"""
WealthLens OSS — AI Advisor Route
POST /api/ai/chat — proxy to Anthropic Claude with portfolio context
"""

from fastapi import APIRouter, Depends
from app.auth import get_current_user, AuthContext
from app.schemas import AIMessageRequest, AIMessageResponse
from app.services.ai_advisor import chat

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=AIMessageResponse)
async def ai_chat(
    req: AIMessageRequest,
    auth: AuthContext = Depends(get_current_user),
):
    """
    Proxy chat to Anthropic Claude API.
    The portfolio context is injected server-side — API key never reaches browser.
    """
    response = await chat(
        messages=req.messages,
        context=req.context,
    )
    return AIMessageResponse(content=response or "No response")
