#!/usr/bin/env python3
"""
scripts/start.py — Start up helper.

1. Waits for PostgreSQL to accept connections
2. Runs Alembic migrations (if available)
3. Starts uvicorn dev server

Usage:
    python scripts/start.py
    python scripts/start.py --production  # disables reload and sets workers=2
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse


def load_env() -> None:
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def parse_db_url() -> tuple[str, int]:
    """Returns (host, port) from DATABASE_URL."""
    url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/script2api")
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or 5432


def wait_for_postgres(host: str, port: int, timeout: int = 60) -> bool:
    """Poll TCP port until PostgreSQL is reachable."""
    print(f"⏳ Waiting for PostgreSQL at {host}:{port} ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print("✅ PostgreSQL is up!")
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(1)
    print(f"❌ PostgreSQL not reachable after {timeout}s")
    return False


def run_migrations() -> int:
    """Run alembic upgrade head if alembic.ini exists."""
    if not os.path.exists("alembic.ini"):
        print("⚠️  alembic.ini not found — skipping migrations")
        return 0
    print("📦 Running Alembic migrations ...")
    return subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])


def start_uvicorn(production: bool = False) -> int:
    """Launch uvicorn server."""
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
    ]
    if production:
        cmd += ["--workers", "2"]
    else:
        cmd.append("--reload")
    print(f"🚀 Starting uvicorn on http://{host}:{port}")
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Script2API server")
    parser.add_argument("--production", action="store_true", help="Production mode (no reload)")
    parser.add_argument("--skip-db-check", action="store_true", help="Skip waiting for PostgreSQL")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip alembic upgrade")
    args = parser.parse_args()

    load_env()

    if not args.skip_db_check:
        host, port = parse_db_url()
        if not wait_for_postgres(host, port):
            return 1

    if not args.skip_migrations:
        if run_migrations() != 0:
            print("⚠️  Migration failed — continuing anyway ...")

    return start_uvicorn(production=args.production)


if __name__ == "__main__":
    sys.exit(main())
