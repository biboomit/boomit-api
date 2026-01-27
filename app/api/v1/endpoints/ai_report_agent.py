

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

@router.get(
    "/ai-agent-configs/{agent_id}",
    response_model=AIReportAgentInDB,
    status_code=status.HTTP_200_OK,
    summary="Get AI report agent by ID",
    description="""
    Returns a specific AI report agent configuration by ID for the authenticated user.
    """,
    responses={
        200: {"description": "Agent returned"},
        404: {"description": "Agent not found or access denied"},
        500: {"description": "Internal server error"},
    }
)
def get_ai_report_agent(
    agent_id: str,
    service: AIReportAgentService = Depends(get_ai_report_agent_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a specific AI report agent configuration by ID for the authenticated user.
    """
    user_id = current_user["sub"]
    try:
        logger.info(f"User {user_id} retrieving AI report agent: {agent_id}")
        return service.get_agent_by_id(agent_id, user_id)
    except ValueError as e:
        logger.warning(f"Agent not found for user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving agent {agent_id} for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve agent. Please try again later.")

@router.delete(
    "/ai-agent-configs/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete AI report agent by ID",
    description="""
    Deletes a specific AI report agent configuration by ID for the authenticated user.
    """,
    responses={
        204: {"description": "Agent deleted successfully"},
        404: {"description": "Agent not found or access denied"},
        500: {"description": "Internal server error"},
    }
)
def delete_ai_report_agent(
    agent_id: str,
    service: AIReportAgentService = Depends(get_ai_report_agent_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a specific AI report agent configuration by ID for the authenticated user.
    """
    user_id = current_user["sub"]
    try:
        logger.info(f"User {user_id} deleting AI report agent: {agent_id}")
        service.delete_agent(agent_id, user_id)
        return None
    except ValueError as e:
        logger.warning(f"Agent not found for deletion by user {user_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id} for user {user_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete agent. Please try again later.")
