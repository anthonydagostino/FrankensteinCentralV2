"""Entry point used by the Docker image and for local development."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
