# filename: app/asgi.py
"""ASGI wrapper (Uvicorn): uvicorn app.asgi:app --host 0.0.0.0 --port 8000"""
_app = None

def _get_asgi_app():
    global _app
    if _app is None:
        from asgiref.wsgi import WsgiToAsgi
        from app import create_app
        _app = WsgiToAsgi(create_app())
    return _app

async def app(scope, receive, send):
    asgi_app = _get_asgi_app()
    return await asgi_app(scope, receive, send)
