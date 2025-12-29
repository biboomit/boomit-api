"""WebSocket connection manager for handling real-time notifications."""

from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections and batch subscriptions.
    
    Attributes:
        active_connections: Dict mapping user_id to their WebSocket connection
        batch_subscriptions: Dict mapping batch_id to set of subscribed user_ids
    """
    
    def __init__(self):
        # user_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # batch_id -> set of user_ids
        self.batch_subscriptions: Dict[str, Set[str]] = {}
    
    async def connect(self, user_id: str, websocket: WebSocket):
        """
        Accept a new WebSocket connection.
        
        Args:
            user_id: The authenticated user's ID
            websocket: The WebSocket connection instance
        """
        await websocket.accept()
        self.active_connections[user_id] = websocket
        print(f"✅ User {user_id} connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, user_id: str):
        """
        Remove a WebSocket connection and clean up subscriptions.
        
        Args:
            user_id: The user ID to disconnect
        """
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"❌ User {user_id} disconnected. Total connections: {len(self.active_connections)}")
        
        # Remove user from all batch subscriptions
        for batch_id in list(self.batch_subscriptions.keys()):
            if user_id in self.batch_subscriptions[batch_id]:
                self.batch_subscriptions[batch_id].discard(user_id)
                # Clean up empty subscription sets
                if not self.batch_subscriptions[batch_id]:
                    del self.batch_subscriptions[batch_id]
    
    def subscribe_to_batch(self, user_id: str, batch_id: str):
        """
        Subscribe a user to notifications for a specific batch.
        
        Args:
            user_id: The user ID to subscribe
            batch_id: The batch ID to subscribe to
        """
        if batch_id not in self.batch_subscriptions:
            self.batch_subscriptions[batch_id] = set()
        
        self.batch_subscriptions[batch_id].add(user_id)
        print(f"📬 User {user_id} subscribed to batch {batch_id}")
    
    def unsubscribe_from_batch(self, user_id: str, batch_id: str):
        """
        Unsubscribe a user from notifications for a specific batch.
        
        Args:
            user_id: The user ID to unsubscribe
            batch_id: The batch ID to unsubscribe from
        """
        if batch_id in self.batch_subscriptions:
            self.batch_subscriptions[batch_id].discard(user_id)
            print(f"📭 User {user_id} unsubscribed from batch {batch_id}")
            
            # Clean up empty subscription sets
            if not self.batch_subscriptions[batch_id]:
                del self.batch_subscriptions[batch_id]
    
    async def notify_batch_completed(self, batch_id: str, data: dict):
        """
        Notify all users subscribed to a batch that it has completed.
        
        Args:
            batch_id: The batch ID that completed
            data: Additional data to send with the notification
        """
        if batch_id not in self.batch_subscriptions:
            print(f"⚠️ No subscribers for batch {batch_id}")
            return
        
        subscribers = self.batch_subscriptions[batch_id].copy()
        print(f"📢 Notifying {len(subscribers)} users about batch {batch_id}")
        
        for user_id in subscribers:
            if user_id in self.active_connections:
                try:
                    websocket = self.active_connections[user_id]
                    await websocket.send_json({
                        "type": "batch_completed",
                        "batch_id": batch_id,
                        **data
                    })
                    print(f"✉️ Notification sent to user {user_id}")
                except Exception as e:
                    print(f"❌ Failed to send notification to user {user_id}: {e}")
                    self.disconnect(user_id)
        
        # Clean up subscriptions for this batch
        del self.batch_subscriptions[batch_id]


# Global singleton instance
manager = ConnectionManager()
