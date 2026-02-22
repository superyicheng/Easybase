# Context Tree

A BM25-based context management system that helps AI work with large knowledge bases across sessions. Store knowledge as small chunks, maintain a structural manifest, and retrieve only what's relevant.

## The Problem

AI performs poorly with too much context, but needs accumulated knowledge to give good answers. Context Tree solves this by keeping knowledge in small, searchable chunks (~200 tokens each) and retrieving only the relevant ones per query. Total context stays small regardless of how much knowledge has accumulated.

## How It Works

```
1. AI reads manifest.md (~500 tokens)
   → Sees all chunks, their summaries, how they connect

2. AI decides what it needs
   → Uses reasoning to bridge vocabulary gaps

3. AI calls BM25 search
   → O(1) hash lookups into the inverted index
   → Returns ranked chunks

4. AI reads returned chunks (~200 tokens each, 3-5 chunks)
   → Total context: ~1500 tokens regardless of corpus size
```

The AI is the semantic layer. It reads the manifest, reasons about relevance, and tells BM25 what to retrieve. BM25 handles fast keyword retrieval. Neither does the other's job.

## Project Structure

```
├── manifest.md       Auto-generated. Always loaded by AI. Project map.
├── index.json        Auto-generated. BM25 inverted index.
├── chunks/           Flat directory. One .md file per knowledge chunk.
│   ├── proj-001.md
│   ├── proj-002.md
│   └── ...
└── ctx.py            Single-file search engine. No external dependencies.
```

## Requirements

- Python 3.6+
- No external dependencies (standard library only)

## Quick Start

```bash
# 1. Create your first chunk
python3 ctx.py add --id proj-001 \
  --summary "API authentication flow — OAuth2 token exchange" \
  --body "The API uses OAuth2 authorization code flow. Tokens expire after 1h..." \
  --domain backend --tags "auth,oauth,tokens"

# 2. Build the index (also runs automatically after add)
python3 ctx.py index

# 3. Search for relevant chunks
python3 ctx.py search "authentication tokens"

# 4. Search + load full content (formatted for LLM context)
python3 ctx.py load "how does auth work" --top 3
```

## Commands

### `index` — Build index and manifest

Reads all `chunks/*.md` files, builds the BM25 inverted index (`index.json`), and regenerates the manifest (`manifest.md`).

```bash
python3 ctx.py index
```

### `search` — Find relevant chunks

Returns ranked chunk IDs with BM25 scores.

```bash
python3 ctx.py search "database migration"
python3 ctx.py search "proj-003"                   # ID lookup
python3 ctx.py search "2026-02-10"                 # Date search
python3 ctx.py search "caching" --top 3            # Limit results
python3 ctx.py search "caching" -v                 # Verbose: show IDF, postings
```

### `load` — Search + display full content

Runs a search, then prints the full chunk bodies formatted for LLM context injection.

```bash
python3 ctx.py load "error handling strategy" --top 3
```

Output format:

```
TASK: error handling strategy
LOADED: proj-001, proj-003, proj-005
CHUNKS: 3 | ~600 tokens

── proj-001 | API error handling — retry logic and circuit breakers | score=3.71 ──
{full body content}

── Cross-References ──
proj-001 → see: proj-003 (logging setup)
```

### `add` — Create a new chunk

Creates a chunk file and rebuilds the index.

```bash
python3 ctx.py add --id proj-005 --summary "Rate limiting — sliding window implementation" \
  --body "The API uses a sliding window counter..." \
  --domain backend \
  --tags "rate-limit,throttle" \
  --depends "proj-001,proj-002"
```

### `stats` — Index statistics

```bash
python3 ctx.py stats
```

Shows: chunk count, unique terms, average document length, posting list stats, highest/lowest df terms with IDF values.

## Chunk Format

Each chunk is a self-contained `.md` file in `chunks/` with YAML frontmatter:

```markdown
---
id: proj-001
domain: backend
summary: API error handling — retry logic and circuit breakers
tags: [error-handling, retry, resilience]
depends: []
updated: 2026-02-05
tokens: ~180
---

{Content body. ~200 tokens. Self-contained.}

→ see: proj-003 (logging setup), proj-007 (monitoring alerts)
```

### Field Purposes

| Field | Indexed | Purpose |
|-------|---------|---------|
| `id` | 3x | Chunk ranks #1 when searched by its own ID |
| `summary` | 2x | Most important for searchability — use specific terms |
| `tags` | 1x | Search aliases not in the summary |
| `domain` | 1x | Domain-level filtering |
| `updated` | 1x | Date becomes searchable (`2026-02-10` → `20260210`, `2026`) |
| `body` | 1x | Full content search |

### Writing Good Summaries

Summaries are the most important field for search quality. Use specific terms with low document frequency.

```
Good: "Rate limiting — sliding window with Redis counters"
Good: "JWT refresh token rotation — silent renewal flow"
Bad:  "How the feature works"
Bad:  "Notes about the API"
```

### Target Size

Aim for ~200 tokens per chunk. Small enough for focused retrieval, large enough to be self-contained. If a topic needs more, split into linked chunks with `depends` and `→ see` references.

## BM25 Modifications

Standard BM25 (k1=1.5, b=0.75) with two modifications:

**Reference Weight** — Chunks that many others depend on are foundational and get a score boost:
```
final_score = W(d) × BM25(d, q)
W(d) = 1 + log(1 + refs(d))
```

**IDF Floor** — Common terms contribute a minimum 0.1 signal instead of zero, acting as a tiebreaker:
```
IDF(t) = max(standard_idf(t), 0.1)
```

## Manifest

`manifest.md` is auto-generated and serves as the AI's map of the knowledge base. It lists every chunk with a one-line summary, dependency links, and a dependency graph. Load it at the start of every session (~500 tokens).

## Use Cases

- **Cross-session memory** — Capture findings, decisions, parameters, and corrections as chunks. They persist across sessions.
- **Large project context** — Keep hundreds of knowledge chunks while only loading the 3-5 relevant ones per query.
- **Any domain** — Software architecture, research notes, configuration references, onboarding docs, debugging history — anything that benefits from structured retrieval.

## License

MIT
