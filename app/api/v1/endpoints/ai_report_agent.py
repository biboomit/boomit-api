

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import logging
from app.schemas.ai_report_agent import AIReportAgentCreate, AIReportAgentInDB
from app.services.ai_report_agent import AIReportAgentService
from app.middleware.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()
service = AIReportAgentService()

def get_ai_report_agent_service() -> AIReportAgentService:
    """Dependency to get the AI report agent service instance."""
    return service

@router.post(
    "/ai-agent-configs",
    response_model=AIReportAgentInDB,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AI report agent configuration",
    description="""
    Creates a new AI report agent configuration for the authenticated user. Maximum 5 agents per user.
    Stores all configuration data, including logo as base64, in BigQuery.
    """,
    responses={
        201: {"description": "Agent created successfully"},
        400: {"description": "Maximum agents reached or invalid data"},
        500: {"description": "Internal server error"},
    }
)
def create_ai_report_agent(
    agent: AIReportAgentCreate,
    service: AIReportAgentService = Depends(get_ai_report_agent_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new AI report agent configuration for the authenticated user.
    """
    user_id = current_user["sub"]
    try:
        logger.info(f"User {user_id} creating AI report agent: {agent.agent_name}")
        return service.create_agent(agent, user_id)
    except ValueError as e:
        logger.warning(f"Validation error for user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating agent for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred. Please contact support.")

@router.get(
    "/ai-agent-configs",
    response_model=List[AIReportAgentInDB],
    status_code=status.HTTP_200_OK,
    summary="List AI report agents for authenticated user",
    description="""
    Returns a list of up to 5 AI report agent configurations created by the authenticated user.
    """,
    responses={
        200: {"description": "List of agents returned"},
        500: {"description": "Internal server error"},
    }
)
def list_ai_report_agents(
    service: AIReportAgentService = Depends(get_ai_report_agent_service),
    current_user: dict = Depends(get_current_user),
):
    """
    List up to 5 AI report agent configurations for the authenticated user.
    """
    user_id = current_user["sub"]
    try:
        logger.info(f"User {user_id} listing AI report agents")
        return service.list_agents(user_id)
    except Exception as e:
        logger.error(f"Error listing agents for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve agents. Please try again later.")
