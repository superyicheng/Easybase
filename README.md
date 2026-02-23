# Easybase

A BM25-based context management system that helps AI work with large knowledge bases across sessions. Store knowledge as small chunks, maintain a structural overview, and retrieve only what's relevant.

---

### What It Does

AI performs poorly with too much context, but needs accumulated knowledge to give good answers. Easybase solves both: knowledge persists as chunk files across sessions, and **every piece of useful information is extracted and delivered to the AI — everything else is abstracted away.**

The knowledge tree abstracts the entire knowledge base into a compact structural overview. When the AI needs specific detail, Easybase retrieves all the relevant chunks in full. The AI always gets complete useful information, never truncated, never diluted by irrelevant content.

### Strengths

- **All useful information, nothing else** — Relevant chunks are loaded in full. Everything outside the query's scope is abstracted in tree summaries — present as structure, not as noise.
- **User-first context** — soul.md gives the AI your background and preferences before any project knowledge.
- **Zero dependencies** — Core engine is a single Python file using only the standard library. MCP server requires one package (`mcp`).
- **Works with any AI** — MCP server for Claude/Cursor, browser extension for ChatGPT/Claude.ai/Gemini.
- **Import your existing projects** — Point Easybase at your project directories during setup and it imports all of them as searchable knowledge, instantly.
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
git clone https://github.com/superyicheng/Easybase.git
cd Easybase
python3 ctx.py init
```

That's it. Init handles everything:

1. **User Profile** — set up soul.md (your preferences, background, context for the AI)
2. **Storage** — what the AI should store, enforcement mode
3. **Project Discovery** — **import all your existing projects at once.** You choose which directories Easybase is allowed to scan (e.g. `~/Projects`, `~/work`). Easybase scans those directories for projects containing AI context files (CLAUDE.md, .cursorrules, README.md, etc.) and imports every project it finds as searchable knowledge chunks. You can select which projects to import, or import all of them. You can always import more later with `python3 ctx.py scan`.
4. **AI Tool Integration** — automatically installs the `mcp` package and registers Easybase as an MCP server (auto-detects Claude Code). The MCP server itself instructs the AI to load Easybase — no config files to edit. For apps that can't be auto-configured (Claude Desktop, Cursor, Windsurf), it prints the exact config to copy. For web AI (ChatGPT, Claude.ai, Gemini), use the browser extension.

After init, start a new session in your AI tool and Easybase loads automatically.

Available MCP tools: `easybase_load`, `easybase_search`, `easybase_add`, `easybase_respond`, `easybase_index`, `easybase_stats`, `easybase_ingest`, `easybase_scan`, `easybase_check`, `easybase_permit`

### Where your data lives

All data is stored in `~/.easybase/` — separate from the code you cloned:

| Path | Contents |
|------|----------|
| `~/.easybase/chunks/` | Knowledge chunks (flat Markdown files, searched by BM25) |
| `~/.easybase/knowledge/` | Tree structure with summaries at each level |
| `~/.easybase/inbox/sessions/` | Auto-captured queries and responses |
| `~/.easybase/logs/changes.log` | Audit trail of all operations |
| `~/.easybase/soul.md` | Your user profile (loaded first every session) |
| `~/.easybase/permission.md` | AI access rules — per-project allowed directories and commands |
| `~/.easybase/config.yaml` | All settings |
| `~/.easybase/index.json` | Search index (regenerated automatically) |

The git clone contains only code — no personal data, no conflicts on `git pull`.
To use a different data location, set `EASYBASE_DIR` to point to your data directory.

---

## Browser Extension — ChatGPT, Claude.ai, Gemini

Adds a floating button to web AI chats. Loads context into the chat input and auto-captures AI responses. All Easybase functions are available through the HTTP server — the extension communicates with it to load context, search, and record responses.

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

**Code** (git clone):
```
Easybase/
├── ctx.py              Core engine (Python stdlib only)
├── mcp_server.py       MCP server (requires: pip install mcp)
├── http_server.py      HTTP server for browser extension (stdlib only)
├── PROTOCOL.md         AI instructions (copied to data dir during init)
├── extension/          Browser extension (Chrome Manifest V3)
└── test_ctx.py         Tests
```

**Data** (`~/.easybase/`):
```
~/.easybase/
├── soul.md             User profile
├── permission.md       AI access rules
├── config.yaml         Settings
├── chunks/             Flat chunk storage for BM25
├── knowledge/          Knowledge tree with summaries
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
- **MCP server:** Python 3.10+. Requires `mcp` package (auto-installed during init).
- **HTTP server:** Python 3.6+. Standard library only.
- **Browser extension:** Chrome, Edge, Brave, or any Chromium browser.

## License

MIT
