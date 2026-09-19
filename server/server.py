#!/usr/bin/env python3
"""枢络 VelaMesh — Server entry point.

Usage:
    python server.py
    # or
    uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
"""

import uvicorn

from app.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
    )
