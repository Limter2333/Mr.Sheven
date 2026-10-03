"""Server entry point: uvicorn server.main:app"""

from server import create_app

app = create_app()