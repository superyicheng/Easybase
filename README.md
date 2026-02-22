# Easybase

A BM25-based context management system that helps AI work with large knowledge bases across sessions. Store knowledge as small chunks, maintain a structural manifest, and retrieve only what's relevant.

---

### What It Does

AI performs poorly with too much context, but needs accumulated knowledge to give good answers. Easybase solves both: knowledge persists as chunk files across sessions, and only the relevant chunks are retrieved per query. **Total context stays ~1500 tokens regardless of how large the knowledge base grows.**

### Strengths

- **Zero dependencies** — Single Python file, standard library only. Drop it into any project.
- **Scales without slowing down** — Search time is proportional to matches, not corpus size. 10 chunks and 10,000 chunks search equally fast for specific terms.
- **Modified BM25 for knowledge bases** — IDF floor prevents common domain terms from being ignored. Reference weighting automatically boosts foundational chunks.
- **AI-native design** — Manifest gives the AI structural understanding; chunks give it detail. The AI bridges vocabulary gaps that pure keyword search can't.
- **Works with any domain** — Software architecture, research, configs, debugging notes, onboarding — anything that benefits from structured retrieval.
- **Human-readable storage** — All chunks are plain Markdown files. No database, no binary formats. Version control friendly.

### Limitations

- **Keyword-based, not semantic** — BM25 matches exact terms. It won't connect "authentication" to "login" unless both words appear. The AI compensates by choosing good search terms, but the retrieval itself is lexical.
- **No automatic chunking** — You write and maintain chunks manually. Good summaries and tags are critical for search quality.
- **Flat structure** — No subdirectories, no hierarchical organization. Everything relies on the `depends` field and the manifest for structure.
- **English-optimized tokenizer** — Stopword list and tokenization rules are designed for English text.

---

## How It Works

```
1. AI reads manifest.md (~500 tokens)
   → Sees all chunks, their summaries, how they connect

2. AI decides what it needs
   → Uses reasoning to bridge vocabulary gaps

3. AI calls BM25 search
   → Looks up query terms in the inverted index
   → Only scores chunks that contain those terms
   → Search time scales with matches, not corpus size

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

## Modified BM25

Standard BM25 (k1=1.5, b=0.75) with two modifications designed for chunk-based knowledge retrieval.

### Scaling Behavior

Search uses a precomputed inverted index: a dictionary mapping each term to the list of chunks that contain it. When a query comes in, the engine looks up each query term and only scores the chunks in those posting lists — it never scans the full corpus. As your knowledge base grows from 10 to 10,000 chunks, search time stays nearly constant for specific queries, because rare terms still appear in only a few chunks. The work is proportional to how many chunks match, not how many exist.

### IDF Floor for Common Keywords

In standard BM25, terms that appear in most documents get an IDF near zero — they contribute almost nothing to the score. This is a problem for knowledge bases where common domain terms (e.g., "API", "model", "config") still carry useful signal. The IDF floor ensures every matching term contributes at least a small amount:

```
IDF(t) = max(standard_idf(t), 0.1)
```

Without the floor, a chunk matching "API" + "rate-limiting" scores the same as one matching only "rate-limiting", because IDF("API") ≈ 0. With the floor, "API" adds 0.1 as a tiebreaker — when two chunks match rare terms equally, the one also matching common terms wins.

### Reference Weight for Foundational Chunks

Chunks that many others depend on are foundational knowledge. They get a score boost so they surface more readily:

```
final_score = W(d) × BM25(d, q)
W(d) = 1 + log(1 + refs(d))
```

A chunk with 3 dependents gets a ~2.4x boost. A leaf chunk with no dependents gets no change (1.0x).

## Manifest

`manifest.md` is auto-generated and serves as the AI's map of the knowledge base. It lists every chunk with a one-line summary, dependency links, and a dependency graph. Load it at the start of every session (~500 tokens).

## Use Cases

- **Cross-session memory** — Capture findings, decisions, parameters, and corrections as chunks. They persist across sessions.
- **Large project context** — Keep hundreds of knowledge chunks while only loading the 3-5 relevant ones per query.
- **Any domain** — Software architecture, research notes, configuration references, onboarding docs, debugging history — anything that benefits from structured retrieval.

## License

MIT
