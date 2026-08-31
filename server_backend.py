#!/usr/bin/env python3
"""Frozen backend entrypoint for Electron sidecar packaging.

Starts uvicorn for web_app:app using CLI args:
  server_backend.py --host 127.0.0.1 --port 8010
"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Ming Salvage Sim Electron backend sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()

    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    from web_app import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
