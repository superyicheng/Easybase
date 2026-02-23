# Easybase Protocol

You have an external knowledge base managed by Easybase. You MUST use it
at every step. Never rely on your own context memory for facts, decisions,
or prior conversation. Everything you need is retrieved through Easybase.

Your knowledge base consists of:
- `soul.md` — User-level context (who they are, preferences, background)
- `knowledge/` — Hierarchical knowledge tree with `_summary.md` at each level
- `chunks/` — Flat storage of detailed knowledge chunks searchable by BM25

## The Mandatory Loop

Every user message MUST follow this exact cycle:

### Step 1: Load (auto-captures the user's message)

```
ctx.py load "paste the user's exact message here"
```

This automatically records the user's prompt and returns:
- soul.md — who the user is, their preferences
- Summaries — abstract background of all knowledge areas
- Matched chunks — full details relevant to this query
- Stale project warnings (if any imported files changed)

### Step 2: Read and reason ONLY from what was returned

- Do NOT reference anything from prior conversation turns
- Do NOT assume you know something — if it wasn't in the load output, search for it
- If you need more detail on a sub-topic:
  ```
  ctx.py search "specific terms"
  ```

### Step 3: Answer the user

Formulate your answer using ONLY what Easybase returned:
user context (soul.md) + abstract background (summaries) + specific details (chunks).

### Step 4: Record your answer

```
ctx.py respond "paste your complete answer here"
```

This automatically records the AI response paired with the original query.

### Step 5: Store new knowledge (if any)

If you learned something new or the user provided new information:
```
ctx.py add --id {id} --summary "{summary}" --body "{content}"
  --tags "{tags}" --depends "{dependencies}" --tree-path "{path}"
```

Then update the relevant `_summary.md` if understanding has changed.

## What "all useful information" means

When you call `ctx.py load`, you receive:
- **Full chunk content** for every chunk that matched the query — nothing truncated, nothing summarized
- **Summaries** for every knowledge area that did NOT match — abstract overviews so you know what exists without loading irrelevant detail

This is the contract: everything relevant is delivered in full. Everything outside the query's scope is present as structure (summaries), not as noise.

## Why you must not rely on memory

Your context window is temporary. Between sessions, you remember nothing.
Even within a session, your context may be compressed or truncated.
Easybase is permanent. Every prompt, every answer, every piece of knowledge
is stored and searchable. Trust the system, not your memory.

## Storing knowledge — writing chunks that BM25 can find

BM25 searches by matching keywords. It cannot understand meaning —
only which words appear in which chunks. When you store a chunk,
you are writing it for two readers: the AI that will read the content
later, and BM25 that will find it by keywords.

### Summary field (most important for search)

The summary is the primary search target. It is indexed at 2x weight.

GOOD summaries use specific terms with low frequency:
  "OAuth2 refresh token rotation — silent renewal with PKCE"
  "PostgreSQL connection pooling — PgBouncer vs pgpool-II tradeoffs"
  "React useMemo performance — when memoization hurts more than helps"

BAD summaries use generic terms that appear in every chunk:
  "How the feature works"
  "Notes about the API"
  "Fix for the bug"

Ask yourself: if someone searched these exact words, would ONLY this
chunk be the right result? If the summary could match 10 other chunks,
it's not specific enough.

### Tags field (search aliases)

Tags exist for terms that someone might search but that aren't in
the summary or body. Think about:
  - Synonyms: if summary says "authentication", add tag "login"
  - Abbreviations: if summary says "PostgreSQL", add tag "postgres"
  - Alternative terms: the user might say "settings" while the chunk
    says "configuration". Add "settings" as a tag.

### Body content

Write for the AI to understand. Include specific values, relationships,
context, and gotchas. The body is indexed at 1x weight — BM25 will
search it, but the summary and tags do the heavy lifting for findability.

### Cross-references

End with → see: lines linking to related chunks. These help both the
AI (reasoning chains) and BM25 (the referenced IDs become searchable
terms in this chunk).

### Depends field

List chunk IDs this knowledge builds on. This feeds the reference
weight system — chunks that many others depend on get boosted in
search results. Foundational knowledge surfaces more easily.

## Splitting a branch

Do NOT split by size. Split when the summary covers genuinely distinct
topics that a human would naturally separate. Create subdirectories,
write new `_summary.md` files, move chunk symlinks.

## Large tasks

1. Decompose into subtasks
2. For EACH subtask: call `ctx.py load` or `ctx.py search` — do not reuse stale context
3. Path summaries (abstract background) stay loaded across subtasks
4. For each subtask, only swap the specific chunks
5. After all subtasks, update summaries with new understanding

## Imported projects

Imported project files live under `knowledge/projects/<name>/` with
chunks in `chunks/proj-*.md`. If `ctx.py load` output shows stale
projects, run `ctx.py scan` to re-import changed files.

## Processing inbox

1. `ctx.py ingest` prepares files for your review
2. YOU decide what knowledge to extract and how to chunk it
3. Create chunks via `ctx.py add` following the storage rules above
4. Update tree summaries
