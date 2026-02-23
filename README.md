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
- **AI-native design** — Tree summaries give abstract background; chunks give specific detail. The AI bridges vocabulary gaps that pure keyword search can't.
- **Works with any AI** — Output of `ctx.py load` is plain text. Paste it into any chat, pipe it to any tool, use it with any API.
- **Works with any domain** — Software, research, documentation, debugging, onboarding — anything that benefits from structured retrieval.
- **Human-readable storage** — All chunks are plain Markdown. No database, no binary formats. Version control friendly.
- **Automatic capture** — Every user prompt and AI response is automatically recorded when the AI follows the protocol. No manual recording needed.
- **Audit trail** — Every operation logged with timestamps to `logs/changes.log`.

### Tradeoffs

- **Keyword-based, not semantic** — BM25 matches exact terms. The AI compensates by choosing good search terms after reading the tree summaries, but the retrieval itself is lexical.
- **Manual chunking** — You (or the AI) write and maintain chunks. This gives full control over what gets stored and how it's summarized.
- **English-optimized tokenizer** — Stopword list and tokenization rules are designed for English text.

---

## Quick Start

```bash
git clone <repo> easybase
cd easybase
python3 ctx.py init
```

Follow the prompts. Init walks through 4 phases:
1. **Identity** — your name, role, and user profile (imports existing CLAUDE.md, .cursorrules, etc. or creates a new soul.md)
2. **Knowledge Base** — name, storage mode, search limits
3. **Project Discovery** — optionally scans your machine for existing projects and imports them as searchable chunks
4. **Confirmation** — prints permissions, data locations, and next steps

Then use `ctx.py load "your question"` to get context blocks.
The soul.md, protocol, and relevant knowledge are automatically included in every output.

## How It Works

```
1. User sends message to AI
2. AI calls ctx.py load "message" — prompt auto-captured
3. AI receives: soul.md + protocol + summaries + relevant chunks
4. AI reads ONLY what was returned — no memory reliance
5. For sub-questions: AI calls ctx.py search
6. AI answers using soul context + structure + specific detail
7. AI calls ctx.py respond "answer" — response auto-captured
8. AI stores new knowledge as chunks (written for BM25 findability)
9. AI updates summaries if understanding changed
```

## Project Structure

```
├── ctx.py            Single-file engine. Python stdlib only.
├── soul.md           User-level context. Loaded first every session.
├── PROTOCOL.md       Instructions for AI. Auto-included in every load output.
├── config.yaml       Generated during init. All settings here.
├── knowledge/        The knowledge tree. Summaries at each level.
│   └── _summary.md   Root summary — AI reads this after soul.md.
├── chunks/           Flat chunk storage for BM25.
├── inbox/            Drop files here for processing.
│   ├── sessions/     Past conversation logs
│   ├── files/        Documents, notes, anything
│   └── processed/    Processed files moved here
├── logs/
│   └── changes.log   Audit trail of all operations
├── index.json        Generated by ctx.py index
└── projects.json     Registry of imported projects
```

## Commands

```bash
# Initialize — interactive setup
python3 ctx.py init

# Build search index from chunks/
python3 ctx.py index

# Search for chunks
python3 ctx.py search "query"
python3 ctx.py search "query" --top 5 --scope api/auth -v

# Get full context block for AI (soul.md + protocol auto-included)
python3 ctx.py load "query" --top 5
python3 ctx.py load "query" --scope api/auth

# Add a chunk (with optional tree placement)
python3 ctx.py add --id api-003 --summary "Rate limiting — sliding window" \
  --body "Content..." --domain backend --tags "throttle,limits" \
  --depends "api-001" --tree-path "api/performance"

# Process inbox files for AI review
python3 ctx.py ingest

# Record AI response (called after answering — auto-captured)
python3 ctx.py respond "AI's complete answer"
python3 ctx.py respond --file /path/to/response.txt

# Record a session manually (for external logs)
python3 ctx.py record --content "session transcript or summary"
python3 ctx.py record --file /path/to/session.log
echo "text" | python3 ctx.py record

# Re-scan for new projects
python3 ctx.py scan
python3 ctx.py scan --paths "~/code,~/projects"

# View statistics
python3 ctx.py stats

# Check system integrity
python3 ctx.py check
```

## soul.md

The soul.md file is loaded at the very top of every `ctx.py load` output,
before the protocol and before any project knowledge. It gives the AI
your general context every session.

During `ctx.py init`, you can:
- **Import an existing file** — If you already have a CLAUDE.md, .cursorrules,
  or any user profile file, Easybase will import it as your soul.md.
- **Create a new one** — Easybase generates a template you fill in with
  your role, preferences, current focus, and notes for the AI.

## Where Everything Lives

Init prints the full paths at the end, but here's the layout:

| Location | What's there | Sensitive? |
|----------|-------------|------------|
| `chunks/` | All knowledge chunks (flat .md files) | Your knowledge |
| `knowledge/` | Tree structure with summaries + symlinks to chunks | Structure only |
| `knowledge/projects/` | Imported project summaries | Snapshots of external files |
| `inbox/sessions/` | Recorded sessions waiting to be processed | Session transcripts |
| `inbox/files/` | Dropped files waiting to be processed | Your files |
| `logs/changes.log` | Timestamped audit trail of all operations | Operation history |
| `config.yaml` | All settings (access mode, scan paths, search params) | Your configuration |
| `soul.md` | Your user profile (loaded first every session) | Personal context |
| `projects.json` | Registry of imported projects (paths, dates) | Project paths |
| `index.json` | Precomputed search index (regenerated by `ctx.py index`) | Derived data |

Everything is stored inside the easybase directory. Nothing is written outside it.

## Managing Projects

During init (Phase 3), Easybase can scan your machine for projects containing AI context files (CLAUDE.md, .cursorrules, README.md, etc.). Found projects are imported as searchable chunks under `knowledge/projects/`.

After init, use `ctx.py scan` to find and import new projects:

```bash
python3 ctx.py scan                          # uses paths from init
python3 ctx.py scan --paths "~/code,~/new"   # scan different paths
```

Imported projects are snapshots — they capture the file contents at import time. The original files are not modified or monitored.

## Recording Sessions

**Automatic capture:** When the AI follows the protocol, every user prompt is auto-captured by `ctx.py load` and every AI response by `ctx.py respond`. These are saved to `inbox/sessions/` with timestamps and type tags (query/response).

**Manual recording** for external session logs:

```bash
python3 ctx.py record --content "summary of what was discussed"
python3 ctx.py record --file /path/to/chat-log.txt
echo "session content" | python3 ctx.py record
```

All recordings go to `inbox/sessions/`. Process them with `ctx.py ingest`, then extract knowledge into chunks.

## Security Model

Easybase is sandboxed by default.

### Sandbox mode (default)

    CAN read/write:  everything inside easybase/
    CANNOT:          access anything outside easybase/
                     access network
                     execute code beyond ctx.py
                     modify ctx.py, PROTOCOL.md, or config.yaml

### Local-read mode (automatic when you scan for projects)

    CAN read:   paths listed in config.yaml allowed_paths (your scan paths)
    CAN write:  only inside easybase/
    CANNOT:     write outside easybase/

### User control

- **config.yaml** — Change storage behavior, search limits, access mode
- **PROTOCOL.md** — Change how the AI uses the system
- **soul.md** — Change your user-level context and preferences
- **logs/changes.log** — Review exactly what the AI stored and when

## Modified BM25

Standard BM25 (k1=1.5, b=0.75) with two modifications designed for knowledge retrieval.

### Scaling Behavior

Search uses a precomputed inverted index. When a query comes in, the engine only scores chunks that contain the query terms — it never scans the full corpus. As the knowledge base grows, search time stays nearly constant for specific queries because rare terms still appear in only a few chunks.

### IDF Floor for Common Keywords

Common domain terms get an IDF near zero in standard BM25. The IDF floor ensures every matching term contributes at least a small amount:

```
IDF(t) = max(standard_idf(t), 0.1)
```

When two chunks match rare terms equally, the one also matching common terms wins.

### Reference Weight for Foundational Chunks

Chunks that many others depend on are foundational knowledge and get a score boost:

```
final_score = W(d) x BM25(d, q)
W(d) = 1 + log(1 + refs(d))
```

## Integration

The output of `ctx.py load` is a text block. Put it before your prompt.

```
Terminal:     ctx.py load "question" | pbcopy
Claude Code:  AI calls ctx.py load (soul + protocol auto-included)
API:          context = subprocess("ctx.py load question")
MCP server:   expose load() as a tool
Any chat:     paste the output into the conversation
```

Every integration gets soul.md and the protocol automatically. No extra setup.

## Requirements

Python 3.6+. Standard library only. No external dependencies.

## License

MIT
