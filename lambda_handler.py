"""AWS Lambda entry point for the API (API Gateway HTTP API / Function URL)."""
from mangum import Mangum

from app.main import app

# lifespan="auto" runs the FastAPI startup hook (bootstrap admin, default rules) on cold start.
handler = Mangum(app, lifespan="auto")
