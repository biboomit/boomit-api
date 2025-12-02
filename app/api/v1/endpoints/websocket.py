"""WebSocket endpoint for real-time batch status notifications."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.connection_manager import manager
from app.middleware.auth import verify_jwt_token
from app.core.exceptions import AuthError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/batch-status/{user_id}")
async def websocket_batch_status(
    websocket: WebSocket, 
    user_id: str
):
    """
    WebSocket endpoint for receiving real-time batch completion notifications.
    
    Authentication:
    - For production: Pass JWT token via Sec-WebSocket-Protocol header
      Example: new WebSocket('ws://api.com/ws/...', ['Bearer.YOUR_JWT_TOKEN'])
    - For development: Token is optional (set WEBSOCKET_AUTH_REQUIRED=false in .env)
    
    Security Note:
    - Tokens are sent via Sec-WebSocket-Protocol header (RFC 6455 standard)
    - This prevents token leakage in server logs, browser history, and referrer headers
    - Query string authentication is deprecated for security reasons
    
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
        user_id: The user's ID (from path parameter)
    """
    # Authentication check (optional for development)
    from app.core.config import settings
    auth_required = settings.WEBSOCKET_AUTH_REQUIRED
    
    # Extract token from Sec-WebSocket-Protocol header
    token = None
    subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    
    # Parse subprotocol: expected format is "Bearer.TOKEN"
    if subprotocols:
        for subprotocol in subprotocols.split(","):
            subprotocol = subprotocol.strip()
            if subprotocol.startswith("Bearer."):
                token = subprotocol[7:]  # Remove "Bearer." prefix
                break
    
    # Accept the connection with the Bearer subprotocol if token was provided
    if token:
        await websocket.accept(subprotocol="Bearer." + token)
    else:
        await websocket.accept()
    
    # Authenticate if required
    if auth_required:
        if not token:
            logger.warning(f"WebSocket connection rejected: no token provided for {user_id}")
            await websocket.close(code=1008, reason="Authentication required - use Sec-WebSocket-Protocol header")
            return
        try:
            payload = verify_jwt_token(token)
            logger.info(f"✅ WebSocket authenticated for user: {user_id}")
        except AuthError as e:
            logger.warning(f"❌ WebSocket authentication failed: {e.message}")
            await websocket.close(code=1008, reason="Authentication failed")
            return
    else:
        logger.info(f"⚠️ WebSocket authentication skipped (development mode) for user: {user_id}")
    
    # Add to connection manager
    manager.active_connections[user_id] = websocket
    logger.info(f"✅ User {user_id} connected. Total connections: {len(manager.active_connections)}")
    
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
