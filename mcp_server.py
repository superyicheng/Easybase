#!/usr/bin/env python3
"""Easybase MCP Server — exposes Easybase tools via Model Context Protocol.

Usage:
    pip install mcp
    python3 mcp_server.py

Data defaults to ~/.easybase. Override with EASYBASE_DIR env var.

Configure in Claude Desktop (claude_desktop_config.json):
    {
        "mcpServers": {
            "easybase": {
                "command": "python3",
                "args": ["/path/to/Easybase/mcp_server.py"],
                "env": {"EASYBASE_DIR": "~/.easybase"}
            }
        }
    }

Configure in Claude Code:
    claude mcp add --scope user --transport stdio easybase \\
        -e EASYBASE_DIR=~/.easybase \\
        -- python3 /path/to/Easybase/mcp_server.py
"""

import os
import sys
import uuid

# Add this directory to path so we can import ctx
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctx

SESSION_ID = uuid.uuid4().hex[:8]

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("easybase", instructions=(
    "You MUST call easybase_load at the start of every conversation "
    "to load context from the Easybase knowledge base. Do this before "
    "responding to the user's first message. After answering, store your "
    "response and any useful external information (files read, web searches, "
    "tool outputs) as chunks via easybase_add."
))

BASE_DIR = os.environ.get("EASYBASE_DIR", os.path.expanduser("~/.easybase"))


@mcp.tool()
def easybase_load(query: str, scope: str = "", session_id: str = "") -> str:
    """Load context from the Easybase knowledge base. Call this FIRST for every user message.

    Returns soul.md + protocol + all matching chunks + full inventory of all chunks.
    The AI should read the returned context and reason ONLY from it.
    All matching chunks are returned — use the full inventory to decide if you
    need to search for more, or if summaries provide enough abstract context.

    Args:
        query: The user's message or search query
        scope: Limit search to a knowledge tree path (e.g. "api/auth")
        session_id: Optional session identifier for concurrent access
    """
    try:
        sid = session_id or SESSION_ID
        return ctx._load_context(query, BASE_DIR, scope=scope or None, session_id=sid)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_search(query: str, scope: str = "") -> str:
    """Search for specific chunks in the knowledge base. Use for follow-up queries after load.

    Returns all matching chunks ranked by relevance. Use summaries from the
    full inventory to decide what additional searches you need.

    Args:
        query: Search terms
        scope: Limit to knowledge tree path (e.g. "api/auth")
    """
    try:
        results = ctx._search_results(query, BASE_DIR, scope=scope or None)
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
                 depends: str = "", tree_path: str = "",
                 session_id: str = "") -> str:
    """Store new knowledge as a chunk. The full response from easybase_respond
    is auto-attached as the body — you do NOT need to paste your answer.
    Focus on writing a good summary and comprehensive synonym tags.

    Args:
        id: Unique chunk ID (e.g. "auth-001")
        summary: Searchable title — indexed at 2x weight, use specific terms
        body: Optional annotation (placed above the auto-attached full response)
        domain: Category (e.g. "backend", "frontend", "devops")
        tags: Comma-separated synonyms and aliases for search (CRITICAL for findability)
        depends: Comma-separated chunk IDs this knowledge builds on
        tree_path: Location in knowledge tree (e.g. "api/auth")
        session_id: Optional session identifier for concurrent access
    """
    try:
        sid = session_id or SESSION_ID
        return ctx._add_chunk(id, summary, body, domain, tags, depends, tree_path, BASE_DIR, session_id=sid)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_respond(response_text: str, session_id: str = "") -> str:
    """Record your response. Call AFTER answering the user.

    If enforcement mode is on, response must contain CITED: [chunk-id-1, chunk-id-2, ...]
    at the end.

    Args:
        response_text: Your complete response to the user
        session_id: Optional session identifier for concurrent access
    """
    try:
        sid = session_id or SESSION_ID
        return ctx._record_response(response_text, BASE_DIR, session_id=sid)
    except ctx.EasybaseError as e:
        return f"Error: {e}"


@mcp.tool()
def easybase_external(action: str, session_id: str = "") -> str:
    """MANDATORY: Declare external source handling after storing your answer.

    You MUST call this after every easybase_add. This forces you to think about
    whether you used external sources (files, web searches, APIs, databases)
    and whether you stored the useful findings.

    Args:
        action: "done" (stored external info as chunks) or "none" (no external sources used)
        session_id: Optional session identifier for concurrent access
    """
    try:
        sid = session_id or SESSION_ID
        return ctx._declare_external(action, BASE_DIR, session_id=sid)
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
def easybase_permit(project: str, permission_type: str, value: str) -> str:
    """Record a permanent permission for a project. Call this when the user says
    "allow forever", "always allow", or grants a persistent permission.

    Args:
        project: Project name, or "global" for permissions that apply everywhere
        permission_type: One of: allow_dir, readonly_dir, block_dir, allow_cmd, block_cmd
        value: The directory path or command (e.g. "/Users/me/project", "git", "npm test")
    """
    try:
        return ctx._add_permission(project, permission_type, value, BASE_DIR)
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
