"""CLI entry-point for ``unifin-server``."""

from __future__ import annotations

import argparse


def main() -> None:
    """Launch the unifin REST API server."""
    parser = argparse.ArgumentParser(description="unifin API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "unifin.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
