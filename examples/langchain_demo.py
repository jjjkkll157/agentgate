"""
Demo: LangChain agent using AgentGate as its tool proxy.

Usage:
  1. Start AgentGate:    agentgate --config tools.yaml
  2. Run this demo:      python langchain_demo.py

AgentGate sits at localhost:9400. Tools are called through it
instead of directly hitting external APIs.
"""

import os
import httpx


def agentgate_search(query: str, limit: int = 5) -> str:
    """Search the web. Actually calls AgentGate which handles the real API."""
    resp = httpx.post(
        "http://localhost:9400/tool/web_search",
        json={"q": query, "count": limit},
        timeout=30,
    )
    data = resp.json()
    if data.get("error"):
        return f"search failed: {data.get('reason')}"
    results = data.get("data", {}).get("web", {}).get("results", [])
    if not results:
        return "no results"
    return "\n".join(
        f"- {r.get('title', '?')}: {r.get('url', '')}"
        for r in results
    )


if __name__ == "__main__":
    # Quick smoke test
    result = agentgate_search("Python httpx retry", limit=3)
    print(result)
