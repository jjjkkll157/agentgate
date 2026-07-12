"""Command-line entry point."""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(prog="agentgate", description="Local reliability proxy for AI agent tools")
    parser.add_argument("--config", "-c", default="tools.yaml", help="path to tools.yaml")
    parser.add_argument("--port", "-p", type=int, default=9400, help="listen port (default: 9400)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"error: config file not found: {args.config!r}", file=sys.stderr)
        print("hint: create a tools.yaml file. see examples/tools.example.yaml", file=sys.stderr)
        sys.exit(1)

    from agentgate.telemetry import setup_logging
    setup_logging(args.log_level)

    import uvicorn
    from agentgate.app import create_app

    app = create_app(args.config)
    print(f"AgentGate v0.1.0 — listening on http://{args.host}:{args.port}")
    print(f"dashboard: http://{args.host}:{args.port}/dashboard")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
