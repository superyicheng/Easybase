# Future Improvements

Improvements identified during benchmarking and development. Each could be implemented as an optional mode that users choose — the current defaults remain unchanged.

---

## 1. Inventory Overhead at Scale

**Problem:** At 10,000 chunks, the full chunk inventory (listing every chunk ID and summary) consumes ~500K tokens per query. This is the dominant cost at large scale — the matched chunks themselves are only ~15, but the inventory lists all 10,000.

**Why it exists:** The inventory lets the AI spot relevant chunks that BM25 missed (different vocabulary). Without it, the AI has no way to know what it doesn't know.

**Improvement:** Offer an inventory mode that users can choose:
- **Full inventory (current default)** — Every chunk listed. Best for small-to-medium knowledge bases. Guarantees the AI can always find anything.
- **Tree-only inventory** — Show only the knowledge tree summaries, not individual chunk listings. Reduces overhead from O(N) to O(tree depth). The AI sees the structure and can search specific branches when needed.
- **Paginated inventory** — Show chunk listings grouped by tree branch. Only expand branches the AI requests. Balances visibility with token cost.

**Impact:** At 10,000 chunks, tree-only mode could reduce per-query overhead from ~500K tokens to ~10K tokens, improving the savings ratio from 4.16x to potentially 30x+.

---

## 2. Semantic Search (Chunks with No Keyword Overlap)

**Problem:** BM25 is keyword-based — it matches exact words. If a chunk contains useful information but shares zero vocabulary with the query, BM25 will not find it. For example, a chunk about "database connection pooling" won't match a query about "why my API is slow" even though connection pooling might be the answer.

**Current mitigations (already built in):**
1. **Synonym tags** — The AI writes comprehensive synonym tags for every chunk. "Database pooling" would get tags like "connection, pool, slow, timeout, performance, latency, db." This bridges most vocabulary gaps in practice.
2. **Full inventory scan** — Every load shows all chunk summaries. The AI is instructed to scan the full list and search for anything relevant that BM25 missed. This catches what tags don't cover.
3. **Protocol enforcement** — The AI is explicitly told to check the inventory after every search. Skipping is flagged as a violation.

**Remaining gap:** Chunks with truly unrelated vocabulary that happen to be useful. In practice this is rare because:
- Good tags cover most synonym gaps
- The inventory scan catches the rest if summaries are descriptive
- The AI writes both tags and summaries, so it can make them findable

**Improvement:** Add optional embedding-based search as a second retrieval layer:
- BM25 runs first (fast, precise, no external dependencies)
- Embedding similarity runs second on the inventory (catches semantic matches BM25 missed)
- Results are merged and deduplicated
- This could be an optional mode: "hybrid search" vs "keyword search (default)"

**Trade-off:** Embedding search requires either an external API (OpenAI, Cohere, local model) or a local embedding model, adding a dependency. The current system has zero external dependencies for search.

---

## 3. Smarter Index Rebuild for Bulk Operations

**Problem:** Every `_add_chunk` call triggers a full index rebuild. At 50 chunks added sequentially, this means 50 rebuilds. The file lock ensures correctness but limits parallel throughput.

**Improvement:** Batch mode for bulk operations:
- `_add_chunk(..., defer_index=True)` — Write the chunk file but skip the rebuild
- `build_index()` — Call once after all chunks are written
- For interactive use (the common case), keep the current per-addition rebuild

**Impact:** Bulk import of 1,000 chunks would go from ~1,000 index rebuilds to 1.

---

## 4. Chunk Deduplication

**Problem:** Over time, the AI may store overlapping or near-duplicate chunks — especially when answering similar questions across sessions.

**Improvement:** Detect and merge similar chunks:
- At add time, check if any existing chunk has high BM25 similarity to the new one
- If overlap is high, offer to merge (append new info to existing chunk) instead of creating a duplicate
- Could be automatic or prompt-based

---

## 5. Chunk Expiry and Relevance Decay

**Problem:** Old chunks about deprecated APIs, outdated decisions, or superseded information stay in the knowledge base indefinitely.

**Improvement:** Optional relevance tracking:
- Track when each chunk was last retrieved
- Surface "stale" chunks (never retrieved in N sessions) for review
- User can archive or delete stale chunks

---

*Each improvement is designed as an optional mode. The current system works well for most use cases — these are for users who push the scale or have specific needs.*
