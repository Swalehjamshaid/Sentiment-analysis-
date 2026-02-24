# File: app/dependencies.py
from typing import Dict, Any, Optional, List
from fastapi import Request, WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

# Global instances for the app
manager = ConnectionManager()

def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Retrieves the user from the session. 
    Returns None if the user is not authenticated.
    """
    user = request.session.get("user")
    return user if user else None
