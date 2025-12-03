"""Endpoints for triggering Cloud Run batch processing jobs."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx
import logging
from google.auth.transport.requests import Request
from google.oauth2 import id_token
import os

from app.middleware.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Cloud Run URLs from environment
EMERGING_THEMES_CLOUD_RUN_URL = os.getenv(
    "EMERGING_THEMES_CLOUD_RUN_URL",
    "https://download-emerging-themes-batch-715418856987.us-central1.run.app"
)

REVIEWS_ANALYSIS_CLOUD_RUN_URL = os.getenv(
    "REVIEWS_ANALYSIS_CLOUD_RUN_URL", 
    "https://download-batch-715418856987.us-central1.run.app"
)


class BatchTriggerRequest(BaseModel):
    """Request model for triggering batch processing."""
    batch_id: str
    app_id: str


def get_cloud_run_token(target_url: str) -> str:
    """
    Generate an ID token for authenticating to Cloud Run.
    
    This works automatically when running in GKE/Cloud Run with proper service account.
    For local development, you need Application Default Credentials configured.
    
    Args:
        target_url: The Cloud Run service URL to authenticate to
        
    Returns:
        ID token string
        
    Raises:
        Exception: If token generation fails
    """
    try:
        # Get ID token for the target Cloud Run service
        # This uses the service account attached to the pod/instance
        auth_req = Request()
        token = id_token.fetch_id_token(auth_req, target_url)
        return token
    except Exception as e:
        logger.error(f"Failed to generate Cloud Run token: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to authenticate with Cloud Run service"
        )


@router.post("/batch/emerging-themes/trigger")
async def trigger_emerging_themes_batch(
    request: BatchTriggerRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger Cloud Run function to process emerging themes batch.
    
    This endpoint acts as a secure proxy between the frontend and Cloud Run:
    - Frontend authenticates with JWT token
    - boomit-api authenticates with Cloud Run using service account
    - User never sees Cloud Run credentials
    
    Args:
        request: BatchTriggerRequest with batch_id and app_id
        current_user: Authenticated user from JWT token
        
    Returns:
        Success response from Cloud Run
        
    Raises:
        HTTPException: If Cloud Run call fails
    """
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("userId")
    logger.info(f"User {user_id} triggering emerging themes batch {request.batch_id}")
    
    # Get authentication token for Cloud Run
    target_url = f"{EMERGING_THEMES_CLOUD_RUN_URL}/upload-data"
    
    try:
        token = get_cloud_run_token(EMERGING_THEMES_CLOUD_RUN_URL)
    except HTTPException:
        # If token generation fails (e.g., local dev), try without auth
        logger.warning("Could not generate Cloud Run token, attempting without auth")
        token = None
    
    # Prepare request to Cloud Run
    headers = {
        "Content-Type": "application/json"
    }
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {
        "batch_id": request.batch_id,
        "app_id": request.app_id
    }
    
    # Call Cloud Run service
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                target_url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            logger.info(f"✅ Successfully triggered Cloud Run for batch {request.batch_id}")
            
            return {
                "status": "success",
                "message": "Batch processing triggered successfully",
                "batch_id": request.batch_id,
                "cloud_run_response": response.json()
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Cloud Run returned error {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Cloud Run error: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Cloud Run: {e}")
            raise HTTPException(
                status_code=503,
                detail="Could not connect to batch processing service"
            )


@router.post("/batch/reviews-analysis/trigger")
async def trigger_reviews_analysis_batch(
    request: BatchTriggerRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger Cloud Run function to process reviews analysis batch.
    
    Similar to emerging themes, but for sentiment analysis.
    
    Args:
        request: BatchTriggerRequest with batch_id and app_id
        current_user: Authenticated user from JWT token
        
    Returns:
        Success response from Cloud Run
        
    Raises:
        HTTPException: If Cloud Run call fails
    """
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("userId")
    logger.info(f"User {user_id} triggering reviews analysis batch {request.batch_id}")
    
    # Get authentication token for Cloud Run
    target_url = f"{REVIEWS_ANALYSIS_CLOUD_RUN_URL}/upload-data"
    
    try:
        token = get_cloud_run_token(REVIEWS_ANALYSIS_CLOUD_RUN_URL)
    except HTTPException:
        logger.warning("Could not generate Cloud Run token, attempting without auth")
        token = None
    
    # Prepare request to Cloud Run
    headers = {
        "Content-Type": "application/json"
    }
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {
        "batch_id": request.batch_id,
        "app_id": request.app_id
    }
    
    # Call Cloud Run service
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                target_url,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            logger.info(f"✅ Successfully triggered Cloud Run for batch {request.batch_id}")
            
            return {
                "status": "success",
                "message": "Batch processing triggered successfully",
                "batch_id": request.batch_id,
                "cloud_run_response": response.json()
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Cloud Run returned error {e.response.status_code}: {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Cloud Run error: {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Cloud Run: {e}")
            raise HTTPException(
                status_code=503,
                detail="Could not connect to batch processing service"
            )
