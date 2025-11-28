"""Webhook endpoints for external service callbacks."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from app.websocket.connection_manager import manager

router = APIRouter(
    prefix="/webhook",
    tags=["webhooks"]
)


class BatchCompletedWebhook(BaseModel):
    """Schema for batch completion webhook payload."""
    
    batch_id: str = Field(..., description="OpenAI batch ID")
    analysis_id: str = Field(..., description="Unique analysis ID (UUID)")
    app_id: str = Field(..., description="Application ID (e.g., com.example.app)")
    total_reviews_analyzed: int = Field(..., description="Number of reviews analyzed")
    analysis_period_start: str = Field(..., description="Start date of analysis period")
    analysis_period_end: str = Field(..., description="End date of analysis period")
    analyzed_at: str = Field(..., description="Timestamp when analysis completed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "batch_abc123",
                "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
                "app_id": "com.example.app",
                "total_reviews_analyzed": 1500,
                "analysis_period_start": "2025-01-01",
                "analysis_period_end": "2025-01-31",
                "analyzed_at": "2025-01-31T10:30:00Z"
            }
        }


@router.post(
    "/batch-completed",
    status_code=status.HTTP_200_OK,
    summary="Webhook for batch completion notification",
    description="""
    This webhook is called by the download-emerging-themes-batch service
    when an OpenAI batch analysis has completed and results have been saved to BigQuery.
    
    It notifies all users subscribed to this batch_id via WebSocket.
    """
)
async def batch_completed_webhook(payload: BatchCompletedWebhook):
    """
    Handle batch completion webhook and notify subscribed users.
    
    Args:
        payload: The batch completion data from download-emerging-themes-batch service
        
    Returns:
        dict: Confirmation message with notification count
    """
    try:
        # Get subscribers before notifying (for count)
        subscribers_count = 0
        if payload.batch_id in manager.batch_subscriptions:
            subscribers_count = len(manager.batch_subscriptions[payload.batch_id])
        
        # Notify all subscribed users via WebSocket
        await manager.notify_batch_completed(
            batch_id=payload.batch_id,
            data={
                "analysis_id": payload.analysis_id,
                "app_id": payload.app_id,
                "total_reviews_analyzed": payload.total_reviews_analyzed,
                "analysis_period_start": payload.analysis_period_start,
                "analysis_period_end": payload.analysis_period_end,
                "analyzed_at": payload.analyzed_at
            }
        )
        
        return {
            "status": "success",
            "message": f"Batch completion notification sent to {subscribers_count} user(s)",
            "batch_id": payload.batch_id,
            "subscribers_notified": subscribers_count
        }
    
    except Exception as e:
        print(f"Error processing batch completion webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process batch completion webhook: {str(e)}"
        )
