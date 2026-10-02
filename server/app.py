"""Server entry point: uvicorn server.app:app"""

from server.app import create_app

app = create_app()