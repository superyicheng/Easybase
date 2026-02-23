<p align="center">
  <img src="logo.png" alt="Easybase" width="120">
</p>

<h1 align="center">Easybase</h1>

<p align="center">A BM25-based context management system that helps AI work with large knowledge bases across sessions.<br>Store knowledge as small chunks, maintain a structural overview, and retrieve only what's relevant.</p>

---

### What It Does

AI performs poorly with too much context, but needs accumulated knowledge to give good answers. Easybase solves both: knowledge persists as chunk files across sessions, and **every piece of useful information is extracted and delivered to the AI — everything else is abstracted away.**

The knowledge tree abstracts the entire knowledge base into a compact structural overview. When the AI needs specific detail, Easybase retrieves all the relevant chunks in full. The AI always gets complete useful information, never truncated, never diluted by irrelevant content.

### Strengths

- **All useful information, nothing else** — Relevant chunks are loaded in full. Everything outside the query's scope is abstracted in tree summaries — present as structure, not as noise.
- **User-first context** — soul.md gives the AI your background and preferences before any project knowledge.
- **Zero dependencies** — Core engine is a single Python file using only the standard library. MCP server requires one package (`mcp`).
- **Works with any AI** — MCP server for Claude/Cursor, browser extension for ChatGPT/Claude.ai/Gemini.
- **Synonym-aware search** — Chunks get comprehensive synonym tags. A search for "authentication" finds chunks about "login" too.
- **Full inventory prevents missed info** — Every load output lists ALL chunks, so the AI can spot what BM25 didn't match.
- **Scales without slowing down** — Search time is proportional to matches, not corpus size. The inverted index never scans the full corpus.
- **AI manages everything** — The AI creates chunks, writes summaries, and maintains the knowledge base. You just use it.
- **Automatic capture** — Every prompt and response is recorded automatically.
- **Human-readable storage** — All chunks are plain Markdown. No database, no binary formats.
- **Audit trail** — Every operation logged with timestamps.

---

## Setup

```bash
git clone https://github.com/YichengLi/Easybase.git
cd Easybase
python3 ctx.py init
```

Init walks you through 4 steps:
1. **User Profile** — set up soul.md (your preferences, background, context for the AI)
2. **Knowledge Base** — name, storage settings
3. **Project Discovery** — optionally scan your machine for existing projects to import
4. **Confirmation** — shows where your data will be stored

### Where your data lives

All data is stored inside the easybase directory you cloned:

| Directory | Contents |
|-----------|----------|
| `chunks/` | Knowledge chunks (flat Markdown files, searched by BM25) |
| `knowledge/` | Tree structure with summaries at each level |
| `inbox/sessions/` | Auto-captured queries and responses |
| `logs/changes.log` | Audit trail of all operations |
| `soul.md` | Your user profile (loaded first every session) |
| `config.yaml` | All settings |
| `index.json` | Search index (regenerated automatically) |

To use a different location, set `EASYBASE_DIR` to point to your data directory.

---

## Integration

### MCP Server — Claude Desktop, Claude Code, Cursor, Windsurf

The AI calls all Easybase tools directly. No manual steps during interaction.

```bash
pip install mcp
```

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "easybase": {
      "command": "python3",
      "args": ["/path/to/easybase/mcp_server.py"],
      "env": { "EASYBASE_DIR": "/path/to/easybase" }
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add --transport stdio easybase \
  -e EASYBASE_DIR=/path/to/easybase \
  -- python3 /path/to/easybase/mcp_server.py
```

**Cursor / Windsurf** — same command/args/env pattern in MCP settings.

Available tools: `easybase_load`, `easybase_search`, `easybase_add`, `easybase_respond`, `easybase_index`, `easybase_stats`, `easybase_ingest`, `easybase_scan`, `easybase_check`

### Browser Extension — ChatGPT, Claude.ai, Gemini

Adds a floating button to web AI chats. Loads context into the chat input. Auto-captures AI responses.

**1. Start the local server:**

```bash
python3 http_server.py
```

**2. Load the extension in Chrome** (or Edge, Brave):

1. Go to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select the `extension/` folder

**3. Use it:** Visit any supported AI chat → click **EB** → enter query → context is injected.

---

## Where Easybase Won't Work

| Platform | Why |
|----------|-----|
| **Mobile apps** (ChatGPT iOS, Claude mobile) | No extensions, no CLI |
| **Desktop apps without MCP** | No tool protocol support |
| **Web AI behind corporate firewalls** | Localhost may be blocked |

---

## Project Structure

```
easybase/
├── ctx.py              Core engine (Python stdlib only)
├── mcp_server.py       MCP server (requires: pip install mcp)
├── http_server.py      HTTP server for browser extension (stdlib only)
├── PROTOCOL.md         AI instructions (auto-included in every load)
├── extension/          Browser extension (Chrome Manifest V3)
├── soul.md             User profile (generated during init)
├── config.yaml         Settings (generated during init)
├── knowledge/          Knowledge tree with summaries
├── chunks/             Flat chunk storage for BM25
├── inbox/              Auto-captured sessions
├── logs/               Audit trail
└── index.json          BM25 search index
```

## Modified BM25

Standard BM25 (k1=1.5, b=0.75) with two modifications:

- **IDF Floor:** `IDF(t) = max(standard_idf(t), 0.1)` — common domain terms still contribute.
- **Reference Weight:** `final_score = W(d) x BM25(d, q)` where `W(d) = 1 + log(1 + refs(d))` — foundational chunks get boosted.

## Requirements

- **Core (ctx.py):** Python 3.6+. Standard library only.
- **MCP server:** Python 3.10+. Requires `pip install mcp`.
- **HTTP server:** Python 3.6+. Standard library only.
- **Browser extension:** Chrome, Edge, Brave, or any Chromium browser.

## License

MIT
