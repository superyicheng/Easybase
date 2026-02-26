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
- All matching chunks are returned in full — there is no artificial limit
- If you need more detail on a sub-topic, search for it:
  ```
  ctx.py search "specific terms"
  ```
- Stop searching when you have enough information to answer. The full
  inventory and summaries give you abstract context for everything else —
  you don't need to load every chunk, only the ones relevant to the question.

### Step 3: Answer the user

Formulate your answer using ONLY what Easybase returned:
user context (soul.md) + abstract background (summaries) + specific details (chunks).

### Step 4: Record your answer

```
ctx.py respond "paste your complete answer here"
```

This records the raw AI response to the session log for auditing.

### Step 5: Store your answer as knowledge (MANDATORY)

Your answers are the most valuable knowledge in the system. Every answer
that contains useful information MUST be stored as a chunk so future
sessions can find it. `respond` only logs to the inbox — it does NOT
make your answer searchable. You MUST call `add` to store it.

**Your full response is auto-attached.** When you called `respond` in
Step 4, the system saved your complete response. The next `add` call
automatically uses it as the chunk body — you do NOT need to paste your
answer into the body field. The body is handled for you.

Your job is to provide good **metadata** for searchability:

```
ctx.py add --id {id} --summary "{specific searchable title}"
  --tags "{comprehensive synonyms}" --tree-path "{path}"
```

**What you control:**
- `id` — descriptive, unique identifier (e.g. `auth-setup-001`)
- `summary` — specific, searchable title (indexed at 2x weight)
- `tags` — comprehensive synonyms so BM25 can find this chunk
- `tree_path` — location in the knowledge tree
- `depends` — links to related chunks
- `body` — optional annotation placed above the auto-attached response

**What the system controls:**
- The full response body — auto-attached from your `respond` call
- If you provide a body, it becomes a preamble above the full response
- If you skip `add` entirely, the system auto-saves your response as a
  safety net (but with poor metadata — so always call `add`)

**What to store:** Any answer that explains something, solves a problem,
makes a decision, provides instructions, or produces useful output.
The only answers you skip are trivial acknowledgments ("ok", "done").

Examples:
- User asks "how do I set up auth?" → `add --id auth-setup-001 --summary "OAuth2 setup with Passport.js and JWT for Express" --tags "login, signin, authentication, credentials, session, passport, jwt"`
- User asks to fix a bug → `add --id bugfix-navbar-001 --summary "Fixed navbar dropdown not closing on outside click" --tags "menu, click, close, dismiss, dropdown, ui, bug"`
- User asks for a code review → `add --id review-api-001 --summary "API endpoint code review — missing validation and error handling" --tags "review, validation, error, endpoint, api"`

Then update the relevant `_summary.md` if understanding has changed.

### Step 6: Store new knowledge from the user (if any)

If the user provided new information, preferences, or decisions in their
message, store those as separate chunks too. User-provided knowledge and
AI-generated answers are both valuable — store both.

### Step 7: Store external information and declare (MANDATORY — ENFORCED)

This step is **technically enforced**. After every `easybase_add` (Step 5),
the system sets a flag. You MUST clear it by calling `easybase_external`.
If you skip this, the next `easybase_load` will flag a VIOLATION.

**Step 7a: Store useful external information**

If you read files, searched the web, queried databases, or used any
external tool while answering, you MUST store the useful information
you found. This is how the knowledge base grows beyond just Q&A — it
captures the sources and findings that informed your answer.

What to store:
- **File contents** — Key facts from files you read. Include the file path.
- **Web search results** — Findings with source URLs.
- **External tool outputs** — Database results, API responses, system info.

How to store:
- One chunk per source or topic — don't dump everything into one chunk
- Include source attribution: file path, URL, tool name
- Extract the useful parts — don't store raw dumps
- Use tree_path: `external/files`, `external/web`, `external/tools`
- Write good summary and tags so BM25 can find it later

**Step 7b: Declare external sources (MANDATORY)**

After storing external info (or if you didn't use any), you MUST call:

```
easybase_external("done")    # I stored external info as chunks
easybase_external("none")    # I did not use any external sources
```

This forces you to actively think: "Did I use external sources? Did I
store them?" You cannot skip this — the system enforces it.

**When to use "none":** You answered purely from Easybase context and
your own knowledge, without reading files, searching the web, or calling
any external tools.

**When to use "done":** You read files, searched the web, queried a
database, or used any external tool — and you stored the useful findings
as chunks via `easybase_add` before calling this.

## What "all useful information" means

When you call `ctx.py load`, you receive:
- **Full chunk content** for every chunk that matched the query — nothing truncated, nothing summarized
- **Summaries** for every knowledge area that did NOT match — abstract overviews so you know what exists without loading irrelevant detail

This is the contract: everything relevant is delivered in full. Everything outside the query's scope is present as structure (summaries), not as noise.

## Checking the full inventory (prevents missed information)

Every `ctx.py load` output includes an "All Chunks" section at the bottom.
This lists EVERY chunk in the knowledge base by ID and summary — not just
the ones that matched your query. Chunks already loaded are marked with *.

After reading the retrieved chunks, you MUST check the All Chunks list:
1. Scan every unloaded chunk's summary
2. If any look relevant to the question, search for them:
   `ctx.py search "terms from that chunk's summary"`
3. Do not skip this step — BM25 may miss chunks with different vocabulary

This prevents the systemic error of "didn't think to search for something."
The full inventory gives you visibility into what BM25 didn't match.

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

### Tags field (search aliases — CRITICAL for findability)

Tags exist for terms that someone might search but that aren't in
the summary or body. BM25 is keyword-only — if a chunk says "login"
but the user searches "authentication", it will MISS without tags.

You MUST generate comprehensive synonym tags for every chunk you store:

  - **Synonyms for every key term** — if summary says "authentication",
    tags MUST include: login, signin, sign-in, auth, sso, credentials
  - **Abbreviations and expanded forms** — "db" and "database", "API" and
    "endpoint", "config" and "configuration", "env" and "environment"
  - **Alternative terms a user might search** — "settings" for "configuration",
    "crash" for "error", "deploy" for "release", "fix" for "patch"
  - **Domain-specific aliases** — "k8s" for "kubernetes", "tf" for "terraform",
    "pg" for "postgresql"
  - **Action variants** — "setup" and "install" and "configure", "delete"
    and "remove" and "uninstall"

This costs you almost nothing (a few extra words) but dramatically improves
search recall. A chunk without good tags is a chunk that will be missed.

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

## Multi-agent and concurrent access

Easybase supports multiple agents working simultaneously. Each MCP
connection gets its own session — obligation tracking (pending store,
external declaration) is per-session and cannot interfere with other
sessions.

### Agent teams

If sub-agents have their own MCP connection to Easybase:
- Each sub-agent stores its own findings directly via `easybase_add`
- The main agent should `easybase_search` before storing to avoid duplicates
- Sub-agents' stored chunks are immediately searchable by all agents

If sub-agents do NOT have MCP access:
- The main agent stores on their behalf
- Include the sub-agent's role or identity in the chunk metadata

### Multiple simultaneous sessions

Multiple Claude Code instances, Cursor sessions, or other MCP clients
can use Easybase at the same time. The index is rebuilt atomically with
file locking — no corruption risk. Chunks added by one session are
immediately available to all others after their next search or load.

## Imported projects

Imported project files live under `knowledge/projects/<name>/` with
chunks in `chunks/proj-*.md`. If `ctx.py load` output shows stale
projects, run `ctx.py scan` to re-import changed files.

## Processing inbox

1. Call `ingest` to read all pending inbox files
2. Review the returned content and decide what knowledge to extract
3. Create chunks via `add` following the storage rules above
4. Update tree summaries

## Permissions — YOU must ask BEFORE the tool asks

Every `ctx.py load` output includes the contents of `permission.md`.
This file records what the user has permanently allowed or blocked,
both globally and per project.

### CRITICAL: Easybase permission check happens FIRST

Before you attempt any action that accesses a directory or runs a
command, you MUST check permission.md and ask the user BEFORE the
action triggers any built-in permission prompt from your host app
(Claude Code, Cursor, etc.).

The order is:
1. You need to access a directory or run a command
2. Check permission.md — is it already allowed?
3. If YES → proceed
4. If BLOCKED → Easybase denies it. After that, the AI and its host
   app can handle the situation however they want — Easybase does
   not interfere further
5. If NOT LISTED → you MUST ask the user NOW, before attempting
   the action, with these exact choices:

> I need to [action]. This is not in your Easybase permissions yet.
> 1. **Allow once** — just this time
> 2. **Allow forever for this project** — save to permissions, never ask again
> 3. **Block forever** — save to permissions, never attempt again

If the user picks "allow forever", call `easybase_permit` to save it,
then proceed with the action:
```
easybase_permit(project="project-name", permission_type="allow_dir", value="/path")
```

If the user picks "block forever", call `easybase_permit` with the
block type:
```
easybase_permit(project="project-name", permission_type="block_dir", value="/path")
```

This way the user answers ONCE through Easybase, and the permission
is recorded permanently. The host app's own permission prompt may
still appear after, but the user has already made their decision
and won't be surprised.

### Permission types
- `allow_dir` — AI can read and write in this directory
- `readonly_dir` — AI can read but must not modify
- `block_dir` — AI must never access
- `allow_cmd` — AI can run this command
- `block_cmd` — AI must never run this command

### Scope
- `project="global"` — applies to all projects and sessions
- `project="my-webapp"` — applies only when working on that project

## Your responsibility

You are responsible for all knowledge management:
- **Storing every useful answer you give** — this is the #1 source of knowledge
- Creating chunks when new information appears from the user
- Writing good summaries and synonym tags for BM25 findability
- Updating tree summaries when understanding changes
- Checking the full inventory to avoid missing relevant information
- Running `ingest` to process inbox files and extract knowledge from them
- Recording permanent permissions when the user grants them

The user should never have to create or manage chunks manually.
If a future session can't find something you answered before, that's a
failure — you should have stored it.

## Tool Names

When using Easybase via MCP server, the commands use these tool names:

| CLI Command | MCP Tool |
|-------------|----------|
| `ctx.py load` | `easybase_load` |
| `ctx.py search` | `easybase_search` |
| `ctx.py add` | `easybase_add` |
| `ctx.py respond` | `easybase_respond` |
| `ctx.py external` | `easybase_external` |
| `ctx.py index` | `easybase_index` |
| `ctx.py stats` | `easybase_stats` |
| `ctx.py ingest` | `easybase_ingest` |
| `ctx.py scan` | `easybase_scan` |
| `ctx.py check` | `easybase_check` |
| `ctx.py permit` | `easybase_permit` |

The protocol loop is the same regardless of how you access Easybase.
When this protocol says `ctx.py load`, use `easybase_load` if you are
running as an MCP tool, or `ctx.py load` if running from the terminal.
