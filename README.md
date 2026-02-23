# Easybase

A knowledge management system for AI. Keeps context short and relevant
across sessions. Deploy once, works with any AI.

---

### What It Does

AI can't hold everything in context and remembers nothing between sessions.
Easybase gives AI a structured external memory:

- A **soul.md** for user-level context — who you are, your preferences, your background
- A **knowledge tree** with abstract summaries at each level
- Small **knowledge chunks** stored flat for fast retrieval
- **Modified BM25 search** that finds all relevant chunks by keyword
- A **protocol** the AI follows to navigate, retrieve, and store knowledge

**Every piece of useful information is extracted and delivered to the AI in full. Everything outside the query's scope is abstracted in the tree summaries — present as structure, not as noise.**

### The Flow

Every interaction follows this cycle:

```
1. User sends a message
2. AI calls ctx.py load "message" — prompt auto-captured, context returned
3. AI reasons using ONLY what Easybase returned, searching for sub-topics as needed
4. AI answers the user
5. AI calls ctx.py respond "answer" — response auto-captured
6. AI stores any new knowledge via ctx.py add
```

The AI never relies on its own memory. Every fact is verified against the knowledge base. Every prompt and response is automatically recorded.

### Strengths

- **All useful information, nothing else** — Relevant chunks are loaded in full. Everything else is abstracted in tree summaries. Never truncated, never diluted.
- **User-first context** — soul.md gives the AI your background and preferences before touching any project knowledge. Bring an existing CLAUDE.md or .cursorrules, or create a fresh one.
- **Zero dependencies** — Single Python file, standard library only. Drop it into any project.
- **Scales without slowing down** — Search time is proportional to matches, not corpus size. The inverted index never scans the full corpus.
- **Modified BM25 for knowledge bases** — IDF floor prevents common domain terms from being ignored. Reference weighting boosts foundational chunks automatically.
- **Synonym-aware search** — Chunks get comprehensive synonym tags. A search for "authentication" finds chunks about "login" too.
- **Full inventory prevents missed info** — Every load output lists ALL chunks, so the AI can spot what BM25 didn't match.
- **AI-native design** — Tree summaries give abstract background; chunks give specific detail. The AI bridges vocabulary gaps that pure keyword search can't.
- **Works with any AI** — MCP server for Claude/Cursor, browser extension for ChatGPT/Claude.ai/Gemini, CLI for everything else.
- **Works with any domain** — Software, research, documentation, debugging, onboarding — anything that benefits from structured retrieval.
- **Human-readable storage** — All chunks are plain Markdown. No database, no binary formats. Version control friendly.
- **Configurable enforcement** — Optional mode where the AI must cite chunk IDs and cannot use its own memory.
- **Automatic capture** — Every user prompt and AI response is automatically recorded when the AI follows the protocol. No manual recording needed.
- **Audit trail** — Every operation logged with timestamps to `logs/changes.log`.

### Tradeoffs

- **No semantic search** — BM25 matches keywords, not meaning. Searching "how to deploy" won't find a chunk about "CI/CD pipeline" unless it has matching tags. Synonym tags reduce this gap significantly, but you need to write good tags.
- **Context window cost** — Every load output includes soul.md + protocol + summaries + matched chunks + full inventory. With a large knowledge base this can consume a significant portion of the AI's context window.
- **Cold start** — An empty knowledge base gives the AI nothing to work with. Value grows only as you (or the AI) add chunks over time.
- **Manual chunking** — No automatic extraction from documents. You or the AI decide what to store and how to split it. Full control, but requires effort.
- **Single-user** — No multi-user access, no authentication, no conflict resolution. One person's knowledge base on one machine.
- **No chunk versioning** — Chunks can be overwritten. The audit log tracks operations but not content diffs.
- **English-optimized tokenizer** — Stopword list and tokenization rules are designed for English text. Other languages will have suboptimal search.
- **Browser extension is limited** — In web-based AI chats (ChatGPT, Claude.ai, Gemini), the AI can read injected context but cannot do follow-up searches or add chunks. Full functionality requires MCP (Claude Desktop, Claude Code, Cursor) or CLI.
- **Fragile web selectors** — The browser extension relies on CSS selectors to find chat input fields. When platforms update their UI, selectors may need updating.

---

## Setup

### Step 1: Download and Initialize

```bash
git clone <repo> easybase
cd easybase
python3 ctx.py init
```

Follow the prompts. Init walks through 4 phases:
1. **Identity** — your name, role, and user profile (imports existing CLAUDE.md, .cursorrules, etc. or creates a new soul.md)
2. **Knowledge Base** — name, storage mode, search limits, enforcement mode
3. **Project Discovery** — optionally scans your machine for existing projects and imports them as searchable chunks
4. **Confirmation** — prints permissions, data locations, and next steps

### Step 2: Choose Your Integration

| Method | Best For | What the AI Can Do |
|--------|----------|-------------------|
| [MCP Server](#mcp-server) | Claude Desktop, Claude Code, Cursor, Windsurf | Everything — load, search, add, respond, index |
| [Browser Extension](#browser-extension) | ChatGPT web, Claude.ai web, Gemini web | Load context, auto-capture responses |
| [CLI / Terminal](#cli--terminal) | Scripts, pipelines, automation | Everything |
| [Manual Paste](#manual-paste) | Any AI chat or app | Load context (copy/paste) |

---

## MCP Server

**For: Claude Desktop, Claude Code, Cursor, Windsurf, and any MCP-compatible app.**

The AI calls Easybase tools directly. All functions work automatically —
load, search, add chunks, record responses, rebuild index, view stats.
This is the most complete integration — no manual steps required.

### Install

```bash
pip install mcp
```

### Claude Desktop

1. Open Claude Desktop
2. Go to Settings > Developer > Edit Config
3. Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "easybase": {
      "command": "python3",
      "args": ["/absolute/path/to/easybase/mcp_server.py"],
      "env": {
        "EASYBASE_DIR": "/absolute/path/to/easybase"
      }
    }
  }
}
```

4. Restart Claude Desktop (Cmd+Q on Mac, not just close)
5. The AI now has these tools: `easybase_load`, `easybase_search`, `easybase_add`, `easybase_respond`, `easybase_index`, `easybase_stats`

### Claude Code

```bash
claude mcp add --transport stdio easybase \
  -e EASYBASE_DIR=/absolute/path/to/easybase \
  -- python3 /absolute/path/to/easybase/mcp_server.py
```

### Cursor / Windsurf

Add to MCP settings with the same command/args/env pattern as Claude Desktop.

### What the AI can do with MCP

- Automatically load context for every user message
- Search for follow-up information
- Store new knowledge as chunks with synonym tags
- Record responses for the audit trail
- Rebuild the index after manual chunk edits
- View knowledge base statistics

---

## Browser Extension

**For: ChatGPT (web), Claude.ai (web), Gemini (web), and any browser-based AI chat.**

Adds a floating "EB" button to supported AI chat pages. Click it, enter your query, and Easybase context is injected directly into the chat input field. AI responses are automatically captured.

### Install

**1. Start the local server** (must be running while using the extension):

```bash
cd /path/to/easybase
python3 http_server.py
```

This starts a local-only server at `http://127.0.0.1:8372`. It never leaves your machine.

**2. Load the extension in Chrome** (or any Chromium browser — Edge, Brave, etc.):

1. Go to `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder inside your easybase directory

**3. Use it:**

1. Visit ChatGPT, Claude.ai, or Gemini
2. Click the blue **EB** button (bottom-right corner)
3. Type your query
4. Click **Load Context** — the context block is injected into the chat input
5. Type your question after the context block and send

### What works with the extension

- Loading full context (soul.md + protocol + matched chunks + full inventory) into any supported web AI chat
- Auto-capture of AI responses — sent to the server automatically after the AI finishes responding
- The AI reads the injected context and follows the Easybase protocol
- Server status shown in extension popup (green = connected)

### What doesn't work with the extension

- The AI cannot call Easybase tools directly (it reads injected text, not tool calls)
- Follow-up searches must be done via CLI — the AI in web chat cannot call search
- Adding chunks must be done via CLI
- For full automation, use MCP instead

### Custom server port

```bash
EASYBASE_PORT=9000 python3 http_server.py
```

Then update the server URL in the extension popup.

---

## CLI / Terminal

**For: Scripts, pipelines, API integrations, and direct terminal use.**

No extra setup beyond `ctx.py init`. All commands work immediately.

```bash
# Get full context block for AI
python3 ctx.py load "your question"
python3 ctx.py load "query" --top 5 --scope api/auth

# Search for specific chunks
python3 ctx.py search "query"
python3 ctx.py search "query" --top 5 -v

# Add a chunk
python3 ctx.py add --id api-003 --summary "Rate limiting — sliding window" \
  --body "Content..." --domain backend --tags "throttle,limits" \
  --depends "api-001" --tree-path "api/performance"

# Record AI response
python3 ctx.py respond "AI's complete answer"

# Build search index
python3 ctx.py index

# Process inbox files
python3 ctx.py ingest

# Record session manually
python3 ctx.py record --content "session transcript"

# Re-scan for projects
python3 ctx.py scan

# View statistics
python3 ctx.py stats

# Check system integrity
python3 ctx.py check
```

### API integration

```python
import subprocess
result = subprocess.run(
    ["python3", "ctx.py", "load", "your question"],
    capture_output=True, text=True
)
context = result.stdout
```

### Pipe to clipboard

```bash
python3 ctx.py load "question" | pbcopy      # macOS
python3 ctx.py load "question" | xclip       # Linux
```

---

## Manual Paste

**For: Any AI chat or app. No setup beyond init.**

Works everywhere — ChatGPT, Claude, Gemini, local models, mobile, anything.

1. Run in terminal: `python3 ctx.py load "your question"`
2. Copy the output
3. Paste into any AI chat
4. The AI reads the protocol and follows it

This is the universal fallback. If nothing else works, manual paste always does.

---

## Where Easybase Won't Work

| Platform | Why | Workaround |
|----------|-----|------------|
| **Mobile apps** (ChatGPT iOS/Android, Claude mobile) | No browser extensions, no CLI access | Copy/paste from a terminal on your computer |
| **Desktop apps without MCP** (older versions, non-MCP apps) | No tool protocol support | Copy/paste from terminal, or upgrade to MCP-compatible version |
| **Web AI behind corporate firewalls** | Extension or localhost may be blocked | Ask IT to allowlist localhost:8372, or use manual paste |
| **Offline environments without Python** | Easybase requires Python 3.6+ | Install Python (Easybase itself works fully offline — no network needed) |

---

## How It Works

```
1. User sends message to AI
2. AI calls easybase_load / ctx.py load — prompt auto-captured
3. AI receives: soul.md + protocol + summaries + matched chunks + full inventory
4. AI reads ONLY what was returned — no memory reliance
5. AI checks All Chunks list for anything BM25 might have missed
6. For sub-questions: AI calls easybase_search / ctx.py search
7. AI answers using soul context + summaries + specific chunks
8. AI calls easybase_respond / ctx.py respond — response auto-captured
9. AI stores new knowledge as chunks with synonym tags
10. AI updates summaries if understanding changed
```

## Project Structure

```
easybase/
├── ctx.py              Core engine (Python stdlib only)
├── mcp_server.py       MCP server (requires: pip install mcp)
├── http_server.py      HTTP server for browser extension (stdlib only)
├── soul.md             User-level context (loaded first every session)
├── PROTOCOL.md         AI instructions (auto-included in every load)
├── config.yaml         Settings (generated during init)
├── extension/          Browser extension (Chrome Manifest V3)
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   ├── popup.html/js
│   ├── styles.css
│   └── icons/
├── knowledge/          Knowledge tree with summaries at each level
│   └── _summary.md
├── chunks/             Flat chunk storage for BM25
├── inbox/
│   ├── sessions/       Auto-captured queries and responses
│   ├── files/          Documents dropped for processing
│   └── processed/      Files moved here after ingest
├── logs/
│   └── changes.log     Audit trail
├── index.json          BM25 index (regenerated by ctx.py index)
└── projects.json       Registry of imported projects
```

## soul.md

Loaded at the very top of every `ctx.py load` output, before the protocol
and before any project knowledge. Gives the AI your general context every session.

During init, you can import an existing CLAUDE.md, .cursorrules, or any
user profile file, or create a fresh template.

## Enforcement Mode

Optional. Controls whether the AI must use ONLY the knowledge base or can
also draw on its own memory.

Enable during `ctx.py init` when prompted, or toggle in `config.yaml`:

```yaml
enforcement:
  citation_required: true
```

**Off (default):** AI uses Easybase as primary source but may also use its own knowledge.

**On:** AI must use ONLY the knowledge base. Every response must end with
`CITED: [chunk-id-1, chunk-id-2, ...]`. The respond command rejects responses
without citations (hard enforcement for MCP/CLI pipelines).

## Security Model

Easybase is sandboxed by default.

- **Sandbox mode (default):** Read/write inside easybase/ only.
- **Local-read mode (when scanning projects):** Can also read your scan paths. Writes stay inside easybase/.
- **HTTP server:** Binds to 127.0.0.1 only (localhost). Never accessible from the network.

## Modified BM25

Standard BM25 (k1=1.5, b=0.75) with two modifications:

- **IDF Floor:** `IDF(t) = max(standard_idf(t), 0.1)` — common domain terms still contribute.
- **Reference Weight:** `final_score = W(d) x BM25(d, q)` where `W(d) = 1 + log(1 + refs(d))` — foundational chunks get boosted.

Search uses a precomputed inverted index. Only scores chunks containing query terms — never scans the full corpus.

## Requirements

- **Core (ctx.py):** Python 3.6+. Standard library only.
- **MCP server:** Python 3.10+. Requires `pip install mcp`.
- **HTTP server:** Python 3.6+. Standard library only.
- **Browser extension:** Chrome, Edge, Brave, or any Chromium browser.

## License

MIT
