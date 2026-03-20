"""
WealthLens OSS — AI Advisor Service (Anthropic Claude proxy)
"""

import httpx
from app.config import settings
from typing import Optional

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are WealthLens AI Advisor — a knowledgeable, concise financial advisor 
for Indian family wealth management. You have access to the family's complete portfolio data 
including holdings, member allocations, goals, and alert rules.

Guidelines:
- Be specific and actionable. Reference actual numbers from the portfolio.
- Consider Indian tax implications (LTCG, STCG, Section 80C, 80D, etc.).
- Suggest rebalancing when allocation drifts beyond typical thresholds.
- For mutual funds, prefer direct plans over regular plans.
- Keep responses concise — max 3-4 paragraphs unless the user asks for detail.
- If you don't have enough data, say so rather than speculating.
"""


async def chat(
    messages: list[dict],
    context: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1000,
) -> Optional[str]:
    """Send a chat message to Claude with portfolio context."""
    if not settings.ANTHROPIC_API_KEY:
        return "AI Advisor is not configured. Please set ANTHROPIC_API_KEY in your environment."

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\n--- PORTFOLIO CONTEXT ---\n{context}"

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }

    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ANTHROPIC_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return text or "No response from AI."
    except httpx.HTTPStatusError as e:
        return f"AI service error: {e.response.status_code}"
    except Exception as e:
        return f"AI service unavailable: {str(e)}"
