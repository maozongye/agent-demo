"""API v1 router configuration.

This module sets up the main API router and includes all sub-routers for different
endpoints like authentication, chatbot, and agent stubs.
"""

from fastapi import APIRouter

from app.api.v1.agents import contract as contract_agent
from app.api.v1.agents import email as email_agent
from app.api.v1.agents import knowledge as knowledge_agent
from app.api.v1.agents import report as report_agent
from app.api.v1.auth import router as auth_router
from app.api.v1.chatbot import router as chatbot_router
from app.core.logging import logger

api_router = APIRouter()

# Include routers
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(contract_agent.router, prefix="/agents/contract", tags=["agents-contract"])
api_router.include_router(email_agent.router, prefix="/agents/email", tags=["agents-email"])
api_router.include_router(report_agent.router, prefix="/agents/report", tags=["agents-report"])
api_router.include_router(knowledge_agent.router, prefix="/agents/knowledge", tags=["agents-knowledge"])


@api_router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        dict: Health status information.
    """
    logger.info("health_check_called")
    return {"status": "healthy", "version": "1.0.0"}
