"""WebSocket endpoint for real-time batch status notifications."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.connection_manager import manager

router = APIRouter()


@router.websocket("/ws/batch-status/{user_id}")
async def websocket_batch_status(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for receiving real-time batch completion notifications.
    
    Client should send messages in the format:
    {
        "action": "subscribe" | "unsubscribe",
        "batch_id": "batch_xxx"
    }
    
    Server will send notifications when a batch completes:
    {
        "type": "batch_completed",
        "batch_id": "batch_xxx",
        "app_id": "com.example.app",
        "analysis_id": "uuid",
        ...
    }
    
    Args:
        websocket: The WebSocket connection
        user_id: The authenticated user's ID (from path parameter)
    """
    await manager.connect(user_id, websocket)
    
    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            
            action = data.get("action")
            batch_id = data.get("batch_id")
            
            if not batch_id:
                await websocket.send_json({
                    "type": "error",
                    "message": "batch_id is required"
                })
                continue
            
            if action == "subscribe":
                manager.subscribe_to_batch(user_id, batch_id)
                await websocket.send_json({
                    "type": "subscribed",
                    "batch_id": batch_id,
                    "message": f"Successfully subscribed to batch {batch_id}"
                })
            
            elif action == "unsubscribe":
                manager.unsubscribe_from_batch(user_id, batch_id)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "batch_id": batch_id,
                    "message": f"Successfully unsubscribed from batch {batch_id}"
                })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}. Use 'subscribe' or 'unsubscribe'"
                })
    
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        print(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(user_id)
