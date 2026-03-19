"""Run the existing FastAPI backend as localhost-only control API."""

from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

load_dotenv(os.environ.get("ENV_FILE", ".env"))


def main() -> None:
    host = os.environ.get("CONTROL_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("CONTROL_API_PORT", "8010"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
