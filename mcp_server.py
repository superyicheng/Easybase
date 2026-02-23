#!/usr/bin/env python3
"""Easybase MCP Server — exposes Easybase tools via Model Context Protocol.

Usage:
    pip install mcp
    python3 mcp_server.py

Configure in Claude Desktop (claude_desktop_config.json):
    {
        "mcpServers": {
            "easybase": {
                "command": "python3",
                "args": ["/path/to/easybase/mcp_server.py"],
                "env": {"EASYBASE_DIR": "/path/to/easybase"}
            }
        }
    }

Configure in Claude Code:
    claude mcp add --transport stdio easybase \\
        -e EASYBASE_DIR=/path/to/easybase \\
        -- python3 /path/to/easybase/mcp_server.py
"""

import os
import sys

# Add this directory to path so we can import ctx
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctx

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("easybase")

BASE_DIR = os.environ.get("EASYBASE_DIR", os.path.dirname(os.path.abspath(__file__)))


@mcp.tool()
def easybase_load(query: str, top_k: int = 10, scope: str = "") -> str:
    """Load context from the Easybase knowledge base. Call this FIRST for every user message.

    Returns soul.md + protocol + relevant chunks + full inventory of all chunks.
    The AI should read the returned context and reason ONLY from it.

    Args:
        query: The user's message or search query
        top_k: Maximum chunks to return (default 10)
        scope: Limit search to a knowledge tree path (e.g. "api/auth")
    """
    try:
        return ctx._load_context(query, BASE_DIR, top_k, scope or None)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_search(query: str, top_k: int = 10, scope: str = "") -> str:
    """Search for specific chunks in the knowledge base. Use for follow-up queries after load.

    Args:
        query: Search terms
        top_k: Maximum results (default 10)
        scope: Limit to knowledge tree path (e.g. "api/auth")
    """
    try:
        results = ctx._search_results(query, BASE_DIR, top_k, scope or None)
        if not results:
            return "No results found."
        lines = [f'Search: "{query}"', ""]
        for rank, r in enumerate(results, 1):
            lines.append(f"{rank}. {r['id']} (score={r['score']}) — {r['summary']}")
        return "\n".join(lines)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_add(id: str, summary: str, body: str = "",
                 domain: str = "", tags: str = "",
                 depends: str = "", tree_path: str = "") -> str:
    """Store new knowledge as a chunk. Include synonym tags for BM25 findability.

    Args:
        id: Unique chunk ID (e.g. "auth-001")
        summary: Searchable title — indexed at 2x weight, use specific terms
        body: Full content of the chunk
        domain: Category (e.g. "backend", "frontend", "devops")
        tags: Comma-separated synonyms and aliases for search (CRITICAL for findability)
        depends: Comma-separated chunk IDs this knowledge builds on
        tree_path: Location in knowledge tree (e.g. "api/auth")
    """
    try:
        return ctx._add_chunk(id, summary, body, domain, tags, depends, tree_path, BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_respond(response_text: str) -> str:
    """Record your response. Call AFTER answering the user.

    If enforcement mode is on, response must contain CITED: [chunk-id-1, chunk-id-2, ...]
    at the end.

    Args:
        response_text: Your complete response to the user
    """
    try:
        return ctx._record_response(response_text, BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_index() -> str:
    """Rebuild the BM25 search index from all chunks. Run after manually editing chunk files."""
    try:
        return ctx._rebuild_index(BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_stats() -> str:
    """Show knowledge base statistics (chunk count, term count, tree depth, etc.)."""
    try:
        return ctx._get_stats(BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_ingest() -> str:
    """Process files in the inbox. Returns file contents for review and chunk extraction."""
    try:
        return ctx._ingest_files(BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_scan(paths: str = "") -> str:
    """Scan for projects and import new ones as searchable chunks.

    Args:
        paths: Comma-separated scan paths (default: uses paths from config)
    """
    try:
        path_list = [p.strip() for p in paths.split(",") if p.strip()] if paths else None
        return ctx._scan_projects(path_list, BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_check() -> str:
    """Validate system integrity — check chunks, index, symlinks, config."""
    try:
        return ctx._check_integrity(BASE_DIR)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
