#!/usr/bin/env python3
"""Easybase — BM25-based context management for AI knowledge bases."""

import json
import math
import os
import re
import sys
from collections import defaultdict

# --- Configuration ---

CHUNKS_DIR = "chunks"
INDEX_FILE = "index.json"
MANIFEST_FILE = "manifest.md"

BM25_K1 = 1.5
BM25_B = 0.75
IDF_FLOOR = 0.1

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "dare", "ought", "used", "it", "its", "this", "that", "these", "those",
    "he", "she", "we", "they", "me", "him", "her", "us", "them",
    "my", "his", "our", "their", "your",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "again", "all", "also", "am",
    "any", "because", "before", "below", "between", "both", "each",
    "few", "further", "here", "how", "into", "more", "most", "much",
    "must", "now", "only", "other", "out", "over", "own", "same",
    "some", "such", "there", "through", "under", "until", "up", "when",
    "where", "which", "while", "who", "whom", "why", "what",
}


# --- Tokenizer ---

def tokenize(text):
    """Tokenize text for BM25 indexing and search."""
    text = text.lower()
    tokens = []

    # Chunk IDs: "cbt-003" → "cbt003"
    for match in re.finditer(r"[a-z]{2,5}-\d{2,4}", text):
        tokens.append(match.group().replace("-", ""))

    # Dates: "2026-02-10" → "20260210" + "2026"
    for match in re.finditer(r"\d{4}-\d{2}-\d{2}", text):
        tokens.append(match.group().replace("-", ""))
        tokens.append(match.group()[:4])

    # Standard words, stopwords removed
    for match in re.finditer(r"[a-z][a-z0-9]+", text):
        word = match.group()
        if word not in STOPWORDS and len(word) > 1:
            tokens.append(word)

    return tokens


# --- YAML Frontmatter Parser ---

def parse_chunk(filepath):
    """Parse a chunk .md file into its components."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter = parts[1].strip()
    body = parts[2].strip()

    # Parse YAML frontmatter (simple key: value)
    meta = {}
    for line in frontmatter.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1]
            if items.strip():
                meta[key] = [item.strip().strip("'\"") for item in items.split(",")]
            else:
                meta[key] = []
        else:
            meta[key] = value.strip("'\"")

    chunk_id = meta.get("id", "")
    summary = meta.get("summary", "")
    tags = meta.get("tags", [])
    domain = meta.get("domain", "")
    date = meta.get("updated", "")
    depends = meta.get("depends", [])

    if isinstance(tags, str):
        tags = [tags] if tags else []
    if isinstance(depends, str):
        depends = [depends] if depends else []

    # Build searchable text with field weights:
    # id×3 + summary×2 + tags×1 + domain×1 + date×1 + body×1
    searchable = " ".join([
        " ".join([chunk_id] * 3),
        " ".join([summary] * 2),
        " ".join(tags),
        domain.replace("-", " "),
        date,
        body,
    ])

    return {
        "id": chunk_id,
        "summary": summary,
        "tags": tags,
        "domain": domain,
        "date": date,
        "depends": depends,
        "body": body,
        "path": os.path.basename(filepath),
        "searchable": searchable,
    }


# --- Index Builder ---

def build_index(base_dir="."):
    """Build BM25 inverted index from all chunks."""
    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    if not os.path.isdir(chunks_dir):
        print(f"Error: {chunks_dir} directory not found.")
        sys.exit(1)

    chunk_files = sorted(f for f in os.listdir(chunks_dir) if f.endswith(".md"))

    if not chunk_files:
        print("Error: No .md files found in chunks/")
        sys.exit(1)

    # Parse all chunks
    chunks = {}
    for fname in chunk_files:
        filepath = os.path.join(chunks_dir, fname)
        chunk = parse_chunk(filepath)
        if chunk and chunk["id"]:
            chunks[chunk["id"]] = chunk

    if not chunks:
        print("Error: No valid chunks parsed.")
        sys.exit(1)

    # Build inverted index
    inverted = defaultdict(lambda: {"df": 0, "postings": {}})
    doc_lengths = {}

    for chunk_id, chunk in chunks.items():
        tokens = tokenize(chunk["searchable"])
        doc_lengths[chunk_id] = len(tokens)

        tf = defaultdict(int)
        for token in tokens:
            tf[token] += 1

        for term, count in tf.items():
            if chunk_id not in inverted[term]["postings"]:
                inverted[term]["df"] += 1
            inverted[term]["postings"][chunk_id] = count

    # Compute reference weights from depends fields
    ref_counts = defaultdict(int)
    for chunk_id, chunk in chunks.items():
        for dep in chunk["depends"]:
            dep = dep.strip()
            if dep and dep != "—":
                ref_counts[dep] += 1

    ref_weights = {}
    for chunk_id in chunks:
        refs = ref_counts.get(chunk_id, 0)
        ref_weights[chunk_id] = 1 + math.log(1 + refs)

    N = len(chunks)
    avgdl = sum(doc_lengths.values()) / N if N > 0 else 0

    chunk_meta = {}
    for chunk_id, chunk in chunks.items():
        chunk_meta[chunk_id] = {
            "summary": chunk["summary"],
            "domain": chunk["domain"],
            "tags": chunk["tags"],
            "date": chunk["date"],
            "path": chunk["path"],
        }

    index = {
        "N": N,
        "avgdl": round(avgdl, 2),
        "k1": BM25_K1,
        "b": BM25_B,
        "doc_lengths": doc_lengths,
        "ref_weights": {k: round(v, 2) for k, v in ref_weights.items()},
        "inverted": {
            term: {"df": data["df"], "postings": data["postings"]}
            for term, data in sorted(inverted.items())
        },
        "chunks": chunk_meta,
    }

    index_path = os.path.join(base_dir, INDEX_FILE)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print(f"Indexed {N} chunks, {len(inverted)} unique terms → {INDEX_FILE}")

    generate_manifest(chunks, base_dir)
    return index


def generate_manifest(chunks, base_dir="."):
    """Generate manifest.md from chunk metadata."""
    domains = set(c["domain"] for c in chunks.values() if c["domain"])

    lines = [
        "# Easybase Manifest",
        "",
        "## Project State",
        f"Knowledge base with {len(chunks)} chunks across {len(domains)} domains.",
        "",
        "## Chunks",
        "",
        "| ID | Summary | Depends On |",
        "|----|---------|------------|",
    ]

    for chunk_id in sorted(chunks.keys()):
        chunk = chunks[chunk_id]
        depends = ", ".join(chunk["depends"]) if chunk["depends"] else "—"
        lines.append(f"| {chunk_id} | {chunk['summary']} | {depends} |")

    lines.append("")
    lines.append("## Dependency Graph")

    # parent ← children
    parent_to_children = defaultdict(list)
    for chunk_id, chunk in chunks.items():
        for dep in chunk["depends"]:
            dep = dep.strip()
            if dep and dep != "—":
                parent_to_children[dep].append(chunk_id)

    if parent_to_children:
        for parent in sorted(parent_to_children.keys()):
            children = sorted(parent_to_children[parent])
            lines.append(f"{parent} ← {', '.join(children)}")
    else:
        lines.append("(no dependencies)")

    lines.append("")

    manifest_path = os.path.join(base_dir, MANIFEST_FILE)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated {MANIFEST_FILE}")


# --- Search ---

def load_index(base_dir="."):
    """Load the precomputed index."""
    index_path = os.path.join(base_dir, INDEX_FILE)
    if not os.path.exists(index_path):
        print(f"Error: {INDEX_FILE} not found. Run 'python3 ctx.py index' first.")
        sys.exit(1)

    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search(query, index, top_k=5, verbose=False):
    """Run modified BM25 search."""
    tokens = tokenize(query)
    if not tokens:
        return []

    N = index["N"]
    avgdl = index["avgdl"]
    k1 = index["k1"]
    b = index["b"]
    inverted = index["inverted"]
    doc_lengths = index["doc_lengths"]
    ref_weights = index["ref_weights"]

    scores = defaultdict(float)

    for token in tokens:
        if token not in inverted:
            if verbose:
                print(f"  [{token}] not in index")
            continue

        entry = inverted[token]
        df = entry["df"]
        postings = entry["postings"]

        idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
        idf = max(idf, IDF_FLOOR)

        if verbose:
            print(f"  [{token}] df={df}, idf={idf:.3f}, postings={list(postings.keys())}")

        for chunk_id, tf in postings.items():
            dl = doc_lengths.get(chunk_id, avgdl)
            tf_sat = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            scores[chunk_id] += idf * tf_sat

    # Apply reference weights
    for chunk_id in scores:
        w = ref_weights.get(chunk_id, 1.0)
        scores[chunk_id] *= w

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    chunks_meta = index.get("chunks", {})
    for chunk_id, score in ranked:
        meta = chunks_meta.get(chunk_id, {})
        results.append({
            "id": chunk_id,
            "score": round(score, 4),
            "summary": meta.get("summary", ""),
            "path": meta.get("path", ""),
        })

    return results


# --- CLI Commands ---

def cmd_search(args, base_dir="."):
    """Search for chunks by query."""
    if not args:
        print("Usage: python3 ctx.py search \"query\" [--top N] [-v]")
        sys.exit(1)

    query = args[0]
    top_k = 5
    verbose = False

    i = 1
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top_k = int(args[i + 1])
            i += 2
        elif args[i] == "-v":
            verbose = True
            i += 1
        else:
            i += 1

    index = load_index(base_dir)
    results = search(query, index, top_k=top_k, verbose=verbose)

    if not results:
        print("No results found.")
        return

    print(f"\nSearch: \"{query}\"")
    print(f"{'Rank':<6}{'ID':<12}{'Score':<10}{'Summary'}")
    print("-" * 60)
    for rank, r in enumerate(results, 1):
        print(f"{rank:<6}{r['id']:<12}{r['score']:<10}{r['summary']}")


def cmd_load(args, base_dir="."):
    """Search + display full chunk content for LLM context."""
    if not args:
        print("Usage: python3 ctx.py load \"query\" [--top N]")
        sys.exit(1)

    query = args[0]
    top_k = 3

    i = 1
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top_k = int(args[i + 1])
            i += 2
        else:
            i += 1

    index = load_index(base_dir)
    results = search(query, index, top_k=top_k)

    if not results:
        print("No results found.")
        return

    # Load chunk files and estimate tokens
    total_tokens = 0
    chunk_contents = []
    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)

    for r in results:
        filepath = os.path.join(chunks_dir, r["path"])
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            chunk_contents.append((r, content))
            total_tokens += len(content) // 4
        else:
            chunk_contents.append((r, f"[File not found: {r['path']}]"))

    ids = ", ".join(r["id"] for r in results)
    print(f"TASK: {query}")
    print(f"LOADED: {ids}")
    print(f"CHUNKS: {len(results)} | ~{total_tokens} tokens")

    for r, content in chunk_contents:
        print(f"\n── {r['id']} | {r['summary']} | score={r['score']} ──")
        # Print body only (skip frontmatter)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                print(parts[2].strip())
            else:
                print(content)
        else:
            print(content)

    # Cross-references
    print(f"\n── Cross-References ──")
    for r, content in chunk_contents:
        refs = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("→ see:") or stripped.startswith("-> see:"):
                refs.append(stripped)
        if refs:
            for ref in refs:
                print(f"{r['id']} {ref}")


def cmd_add(args, base_dir="."):
    """Add a new chunk file and rebuild index."""
    chunk_id = ""
    summary = ""
    body = ""
    domain = ""
    tags = ""
    depends = ""

    i = 0
    while i < len(args):
        if args[i] == "--id" and i + 1 < len(args):
            chunk_id = args[i + 1]
            i += 2
        elif args[i] == "--summary" and i + 1 < len(args):
            summary = args[i + 1]
            i += 2
        elif args[i] == "--body" and i + 1 < len(args):
            body = args[i + 1]
            i += 2
        elif args[i] == "--domain" and i + 1 < len(args):
            domain = args[i + 1]
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = args[i + 1]
            i += 2
        elif args[i] == "--depends" and i + 1 < len(args):
            depends = args[i + 1]
            i += 2
        else:
            i += 1

    if not chunk_id or not summary:
        print("Usage: python3 ctx.py add --id ID --summary \"...\" --body \"...\" "
              "[--domain DOMAIN] [--tags \"t1,t2\"] [--depends \"id1,id2\"]")
        sys.exit(1)

    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    depends_list = [d.strip() for d in depends.split(",") if d.strip()] if depends else []

    from datetime import date
    today = date.today().isoformat()
    token_est = len(body) // 4 if body else 0

    lines = ["---"]
    lines.append(f"id: {chunk_id}")
    if domain:
        lines.append(f"domain: {domain}")
    lines.append(f"summary: {summary}")
    if tags_list:
        lines.append(f"tags: [{', '.join(tags_list)}]")
    if depends_list:
        lines.append(f"depends: [{', '.join(depends_list)}]")
    lines.append(f"updated: {today}")
    lines.append(f"tokens: ~{token_est}")
    lines.append("---")
    lines.append("")
    if body:
        lines.append(body)
    lines.append("")

    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    os.makedirs(chunks_dir, exist_ok=True)
    filepath = os.path.join(chunks_dir, f"{chunk_id}.md")

    if os.path.exists(filepath):
        print(f"Warning: {filepath} already exists. Overwriting.")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Created {filepath}")
    build_index(base_dir)


def cmd_stats(base_dir="."):
    """Show index statistics."""
    index = load_index(base_dir)

    N = index["N"]
    inverted = index["inverted"]
    avgdl = index["avgdl"]

    unique_terms = len(inverted)

    posting_lengths = [entry["df"] for entry in inverted.values()]
    avg_posting = sum(posting_lengths) / len(posting_lengths) if posting_lengths else 0
    max_entry = max(inverted.items(), key=lambda x: x[1]["df"]) if inverted else ("", {"df": 0})

    df1_count = sum(1 for entry in inverted.values() if entry["df"] == 1)

    sorted_by_df_desc = sorted(inverted.items(), key=lambda x: x[1]["df"], reverse=True)[:5]
    sorted_by_df_asc = sorted(inverted.items(), key=lambda x: x[1]["df"])[:3]

    def compute_idf(df):
        idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
        return max(idf, IDF_FLOOR)

    print("=== Easybase Index Stats ===")
    print(f"Chunks (N):          {N}")
    print(f"Unique terms:        {unique_terms}")
    print(f"Avg doc length:      {avgdl:.1f} tokens")
    print(f"Avg posting length:  {avg_posting:.2f}")
    print(f"Max posting list:    \"{max_entry[0]}\" (df={max_entry[1]['df']})")
    print(f"Terms with df=1:     {df1_count}")

    print("\nTop-5 highest df terms:")
    for term, entry in sorted_by_df_desc:
        print(f"  {term:<20} df={entry['df']:<4} idf={compute_idf(entry['df']):.3f}")

    print("\nBottom-3 lowest df terms:")
    for term, entry in sorted_by_df_asc:
        print(f"  {term:<20} df={entry['df']:<4} idf={compute_idf(entry['df']):.3f}")


# --- Main ---

def main():
    if len(sys.argv) < 2:
        print("Easybase — BM25-based context management")
        print()
        print("Commands:")
        print("  index                          Build index + manifest from chunks/")
        print("  search \"query\" [--top N] [-v]   Search for chunks")
        print("  load \"query\" [--top N]          Search + load full chunk content")
        print("  add --id ID --summary \"...\"     Add a new chunk")
        print("  stats                          Show index statistics")
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "index":
        build_index()
    elif cmd == "search":
        cmd_search(args)
    elif cmd == "load":
        cmd_load(args)
    elif cmd == "add":
        cmd_add(args)
    elif cmd == "stats":
        cmd_stats()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
