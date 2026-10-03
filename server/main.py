"""Server entry point: uvicorn server.main:app"""

from server.app import create_app

app = create_app()