#!/usr/bin/env python3
"""Easybase — BM25-based context management for AI knowledge bases."""

import io
import json
import math
import os
import platform
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class EasybaseError(Exception):
    """Raised instead of sys.exit() in internal functions."""
    pass


BANNER = r"""
  ___                _
 | __|__ _ ____  _  | |__  __ _ ___ ___
 | _|/ _` (_-< || | | '_ \/ _` (_-</ -_)
 |___\__,_/__/\_, | |_.__/\__,_/__/\___|
              |__/
"""

DEFAULT_DATA_DIR = os.path.expanduser("~/.easybase")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_base_dir(base_dir=None):
    """Resolve the data directory. Priority: explicit arg > EASYBASE_DIR env > ~/.easybase"""
    if base_dir is not None:
        return base_dir
    return os.environ.get("EASYBASE_DIR", DEFAULT_DATA_DIR)

# --- Defaults ---

CHUNKS_DIR = "chunks"
KNOWLEDGE_DIR = "knowledge"
INBOX_DIR = "inbox"
LOGS_DIR = "logs"
INDEX_FILE = "index.json"
CONFIG_FILE = "config.yaml"
PROTOCOL_FILE = "PROTOCOL.md"
SOUL_FILE = "soul.md"
PERMISSION_FILE = "permission.md"
CHANGES_LOG = "logs/changes.log"
PROJECTS_FILE = "projects.json"
PENDING_STORE_FILE = ".pending_store"

SCAN_TARGETS = [
    "CLAUDE.md", ".cursorrules", ".cursorignore",
    "AGENTS.md", ".github/copilot-instructions.md",
    "README.md", "CONVENTIONS.md",
]

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "env",
    ".env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "target", "vendor",
}

DEFAULT_SCAN_PATHS_MACOS = [
    "~/Desktop", "~/Documents", "~/Developer", "~/Projects", "~/repos", "~/code",
]

DEFAULT_SCAN_PATHS_LINUX = [
    "~/Desktop", "~/Documents", "~/projects", "~/repos", "~/code", "~/src",
]

DEFAULT_K1 = 1.5
DEFAULT_B = 0.75
DEFAULT_IDF_FLOOR = 0.1

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


# --- Simple YAML Parser ---

def _strip_yaml_comment(line):
    """Remove inline YAML comment, preserving # inside quotes."""
    in_quote = False
    quote_char = None
    for i, ch in enumerate(line):
        if ch in ('"', "'") and not in_quote:
            in_quote = True
            quote_char = ch
        elif ch == quote_char and in_quote:
            in_quote = False
        elif ch == '#' and not in_quote:
            return line[:i].rstrip()
    return line


def _parse_yaml_value(value):
    """Parse a single YAML value."""
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [v.strip().strip('"').strip("'") for v in inner.split(',')]
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass
    return value


def parse_yaml(text):
    """Parse simple 2-level YAML (sufficient for config.yaml)."""
    result = {}
    section = None
    list_key = None

    for raw_line in text.split('\n'):
        line = _strip_yaml_comment(raw_line)
        stripped = line.strip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip())

        if stripped.startswith('- ') and section and list_key:
            item = stripped[2:].strip().strip('"').strip("'")
            if section in result and list_key in result[section]:
                result[section][list_key].append(item)
            continue

        if ':' not in stripped:
            continue

        key, _, value = stripped.partition(':')
        key = key.strip()
        value = value.strip()

        if indent == 0:
            if value:
                result[key] = _parse_yaml_value(value)
                section = None
            else:
                result[key] = {}
                section = key
            list_key = None
        elif section is not None:
            if value:
                result[section][key] = _parse_yaml_value(value)
                list_key = None
            else:
                result[section][key] = []
                list_key = key

    return result


def generate_yaml(config):
    """Generate YAML string from a config dict."""
    lines = [
        "# Easybase Configuration",
        "# Edit this file to change behavior. No code changes needed.",
        "",
    ]

    comment_map = {
        ("storage", "mode"): "# all | selective | manual",
        ("access", "mode"): "# sandbox | local-read",
        ("access", "allowed_paths"): "# only used if mode is local-read",
        ("scan", "paths"): "# directories to scan for projects",
        ("scan", "max_depth"): "# how deep to scan (default 3)",
        ("enforcement", "citation_required"): "# true = AI must cite chunks and not use own memory",
    }

    for section_key, section_val in config.items():
        if isinstance(section_val, dict):
            lines.append(f"{section_key}:")
            for key, value in section_val.items():
                comment = comment_map.get((section_key, key), "")
                if isinstance(value, list):
                    if not value:
                        suffix = f"  {comment}" if comment else ""
                        lines.append(f"  {key}: []{suffix}")
                    else:
                        lines.append(f"  {key}:")
                        for item in value:
                            lines.append(f'    - "{item}"')
                elif isinstance(value, bool):
                    lines.append(f"  {key}: {'true' if value else 'false'}")
                elif isinstance(value, str):
                    suffix = f"  {comment}" if comment else ""
                    lines.append(f'  {key}: "{value}"{suffix}')
                else:
                    lines.append(f"  {key}: {value}")
            lines.append("")
        else:
            lines.append(f"{section_key}: {section_val}")

    return '\n'.join(lines) + '\n'


# --- Config ---

def _default_config(storage_mode="all", access_mode="sandbox",
                    scan_paths=None, enforcement=False):
    if scan_paths is None:
        scan_paths = []
    allowed_paths = scan_paths if access_mode == "local-read" else []
    return {
        "storage": {"mode": storage_mode},
        "access": {"mode": access_mode, "allowed_paths": allowed_paths},
        "scan": {"paths": scan_paths, "max_depth": 3},
        "enforcement": {"citation_required": enforcement},
        "search": {
            "bm25_k1": DEFAULT_K1,
            "bm25_b": DEFAULT_B,
            "idf_floor": DEFAULT_IDF_FLOOR,
        },
        "tree": {"sibling_read": True},
    }


def load_config(base_dir=None):
    """Load config.yaml, falling back to defaults."""
    base_dir = _resolve_base_dir(base_dir)
    config_path = os.path.join(base_dir, CONFIG_FILE)
    if not os.path.exists(config_path):
        return _default_config()

    with open(config_path, 'r', encoding='utf-8') as f:
        config = parse_yaml(f.read())

    config.setdefault("storage", {"mode": "all"})
    config.setdefault("access", {"mode": "sandbox", "allowed_paths": []})
    sc = config.setdefault("scan", {})
    sc.setdefault("paths", [])
    sc.setdefault("max_depth", 3)
    s = config.setdefault("search", {})
    s.setdefault("bm25_k1", DEFAULT_K1)
    s.setdefault("bm25_b", DEFAULT_B)
    s.setdefault("idf_floor", DEFAULT_IDF_FLOOR)
    config.setdefault("tree", {"sibling_read": True})
    e = config.setdefault("enforcement", {})
    e.setdefault("citation_required", False)

    return config


# --- Store Enforcement ---

def _set_pending_store(query, base_dir):
    """Mark that a load was called and an answer storage is expected."""
    path = os.path.join(base_dir, PENDING_STORE_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(query[:200])

def _clear_pending_store(base_dir):
    """Mark that the AI stored its answer (called after easybase_add)."""
    path = os.path.join(base_dir, PENDING_STORE_FILE)
    if os.path.exists(path):
        os.remove(path)

def _check_pending_store(base_dir):
    """Check if the AI skipped storing its answer from the previous load.
    Returns the previous query if skipped, None otherwise."""
    path = os.path.join(base_dir, PENDING_STORE_FILE)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

def _store_reminder():
    """Return the mandatory store reminder appended to every load output."""
    return (
        "\n\n# !! MANDATORY: Store your answer !!\n"
        "After you answer, you MUST call easybase_add to store your answer as a chunk.\n"
        "easybase_respond only logs to inbox — it does NOT make your answer searchable.\n"
        "If you skip this, the next easybase_load will flag a VIOLATION.\n"
        "Only skip for trivial responses (\"ok\", \"done\", single-word acknowledgments).\n"
    )


# --- Logging ---

def log_change(message, base_dir=None):
    """Append a line to the audit log."""
    base_dir = _resolve_base_dir(base_dir)
    log_path = os.path.join(base_dir, CHANGES_LOG)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"{ts} {message}\n")


# --- Project Discovery ---

def _get_default_scan_paths():
    """Return default scan paths based on OS."""
    if platform.system() == "Darwin":
        return DEFAULT_SCAN_PATHS_MACOS
    return DEFAULT_SCAN_PATHS_LINUX


def _find_projects(scan_paths, max_depth=3, exclude_dir=None):
    """Walk scan_paths looking for directories containing SCAN_TARGETS files."""
    projects = {}  # path -> {"name", "path", "files"}

    for scan_root in scan_paths:
        scan_root = os.path.expanduser(scan_root)
        if not os.path.isdir(scan_root):
            continue

        for root, dirs, files in os.walk(scan_root):
            # Depth check
            rel = os.path.relpath(root, scan_root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > max_depth:
                dirs.clear()
                continue

            # Skip hidden and ignored directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

            # Skip the easybase directory itself
            if exclude_dir and os.path.abspath(root) == os.path.abspath(exclude_dir):
                dirs.clear()
                continue

            # Check for scan target files
            found = []
            for target in SCAN_TARGETS:
                if os.sep in target or '/' in target:
                    # Nested file like .github/copilot-instructions.md
                    full = os.path.join(root, target)
                    if os.path.isfile(full):
                        found.append(target)
                elif target in files:
                    found.append(target)

            if found:
                abs_root = os.path.abspath(root)
                if abs_root not in projects:
                    projects[abs_root] = {
                        "name": os.path.basename(root),
                        "path": abs_root,
                        "files": found,
                    }
                else:
                    # Merge files if same directory found via multiple scan paths
                    for f in found:
                        if f not in projects[abs_root]["files"]:
                            projects[abs_root]["files"].append(f)

    return list(projects.values())


def _basic_auto_tags(text, max_tags=10):
    """Extract top meaningful keywords from text for auto-tagging."""
    tokens = tokenize(text)
    if not tokens:
        return []
    counts = defaultdict(int)
    for t in tokens:
        counts[t] += 1
    # Sort by frequency, take top N
    sorted_terms = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [term for term, _ in sorted_terms[:max_tags]]


def _extract_summary(body, proj_name, filename):
    """Extract a meaningful summary from file content.

    Tries to find: first markdown heading, then first non-empty paragraph.
    Falls back to 'ProjectName — filename' if nothing useful is found.
    """
    fallback = f"{proj_name} \u2014 {filename}"

    # Try to extract the first markdown heading
    heading_match = re.search(r'^#{1,3}\s+(.+)', body, re.MULTILINE)
    heading = heading_match.group(1).strip() if heading_match else ""

    # Try to extract first meaningful paragraph (non-heading, non-empty, non-comment)
    first_para = ""
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("<!--") or line.startswith("---"):
            continue
        if len(line) > 20:
            first_para = line[:150]
            break

    if heading and first_para:
        return f"{proj_name}/{filename}: {heading} \u2014 {first_para}"
    elif heading:
        return f"{proj_name}/{filename}: {heading}"
    return fallback


def _sanitize_id(name):
    """Convert a project name to a safe chunk ID component."""
    sanitized = re.sub(r'[^a-z0-9]', '-', name.lower())
    sanitized = re.sub(r'-+', '-', sanitized).strip('-')
    return sanitized[:30] if sanitized else "unknown"


def _import_project_file(project, base_dir=None):
    """Import a found project's files as chunks."""
    base_dir = _resolve_base_dir(base_dir)
    proj_name = project["name"]
    safe_name = _sanitize_id(proj_name)
    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    knowledge_dir = os.path.join(base_dir, KNOWLEDGE_DIR)
    tree_path = f"projects/{safe_name}"
    tree_dir = os.path.join(knowledge_dir, tree_path)
    os.makedirs(tree_dir, exist_ok=True)
    os.makedirs(chunks_dir, exist_ok=True)

    imported = []
    today = datetime.now().strftime("%Y-%m-%d")

    for i, filename in enumerate(project["files"]):
        filepath = os.path.join(project["path"], filename)
        if not os.path.isfile(filepath):
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                body = f.read()
        except (UnicodeDecodeError, PermissionError):
            continue

        # Truncate very large files
        if len(body) > 50000:
            body = body[:50000] + "\n\n[Truncated — original file exceeds 50KB]"

        # Generate unique chunk ID
        file_tag = _sanitize_id(filename.replace('.', '-').replace('/', '-'))
        chunk_id = f"proj-{safe_name}-{file_tag}"

        tags = [filename.replace('/', '-'), "project", "imported"]
        # Auto-generate keyword tags from file content
        auto_tags = _basic_auto_tags(body)
        for t in auto_tags:
            if t not in tags:
                tags.append(t)
        summary = _extract_summary(body, proj_name, filename)

        lines = ["---"]
        lines.append(f"id: {chunk_id}")
        lines.append(f"domain: project")
        lines.append(f"summary: {summary}")
        lines.append(f"tags: [{', '.join(tags)}]")
        lines.append(f"depends: []")
        lines.append(f"tree_path: {tree_path}")
        lines.append(f"updated: {today}")
        lines.append("---")
        lines.append("")
        lines.append(body)
        lines.append("")

        chunk_path = os.path.join(chunks_dir, f"{chunk_id}.md")
        with open(chunk_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

        # Create symlink in knowledge tree
        link_path = os.path.join(tree_dir, f"{chunk_id}.md")
        chunk_abs = os.path.abspath(chunk_path)
        link_abs = os.path.abspath(link_path)
        rel_target = os.path.relpath(chunk_abs, os.path.dirname(link_abs))

        if os.path.exists(link_path) or os.path.islink(link_path):
            os.remove(link_path)
        os.symlink(rel_target, link_path)

        imported.append(chunk_id)

    # Create _summary.md for this project branch
    if imported:
        summary_path = os.path.join(tree_dir, "_summary.md")
        summary_lines = [
            f"# {proj_name}",
            "",
            f"Source: `{project['path']}`",
            "",
            "## Imported Files",
        ]
        for filename in project["files"]:
            summary_lines.append(f"- {filename}")
        summary_lines.append("")

        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(summary_lines))

    return imported


def _import_projects(projects, base_dir=None):
    """Import multiple projects and save registry."""
    base_dir = _resolve_base_dir(base_dir)
    all_imported = []

    for proj in projects:
        imported = _import_project_file(proj, base_dir)
        all_imported.extend(imported)
        if imported:
            log_change(f'IMPORT project:{proj["name"]} chunks:{",".join(imported)}', base_dir)

    # Ensure projects/ _summary.md exists
    projects_tree = os.path.join(base_dir, KNOWLEDGE_DIR, "projects")
    if os.path.isdir(projects_tree):
        summary_path = os.path.join(projects_tree, "_summary.md")
        if not os.path.exists(summary_path):
            lines = ["# Projects", ""]
            for proj in projects:
                lines.append(f"- **{proj['name']}** — `{proj['path']}` ({len(proj['files'])} files)")
            lines.append("")
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))

    # Save projects registry
    registry = _load_projects_registry(base_dir)
    today = datetime.now().strftime("%Y-%m-%d")
    for proj in projects:
        registry[proj["path"]] = {
            "name": proj["name"],
            "path": proj["path"],
            "files": proj["files"],
            "imported": today,
        }
    _save_projects_registry(registry, base_dir)

    # Rebuild index if any chunks were created
    if all_imported:
        build_index(base_dir)

    return all_imported


def _load_projects_registry(base_dir=None):
    """Load projects.json registry."""
    base_dir = _resolve_base_dir(base_dir)
    path = os.path.join(base_dir, PROJECTS_FILE)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_projects_registry(registry, base_dir=None):
    """Save projects.json registry."""
    base_dir = _resolve_base_dir(base_dir)
    path = os.path.join(base_dir, PROJECTS_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)


# --- Tokenizer ---

def tokenize(text):
    """Tokenize text for BM25 indexing and search."""
    text = text.lower()
    tokens = []

    for match in re.finditer(r"[a-z]{2,5}-\d{2,4}", text):
        tokens.append(match.group().replace("-", ""))

    for match in re.finditer(r"\d{4}-\d{2}-\d{2}", text):
        tokens.append(match.group().replace("-", ""))
        tokens.append(match.group()[:4])

    for match in re.finditer(r"[a-z][a-z0-9]+", text):
        word = match.group()
        if word not in STOPWORDS and len(word) > 1:
            tokens.append(word)

    return tokens


# --- Chunk Parser ---

def parse_chunk(filepath):
    """Parse a chunk .md file into its components."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.startswith("---"):
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter = parts[1].strip()
    body = parts[2].strip()

    meta = {}
    for line in frontmatter.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip()
        if value.startswith('[') and value.endswith(']'):
            items = value[1:-1]
            if items.strip():
                meta[key] = [item.strip().strip("'\"") for item in items.split(',')]
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
    tree_path = meta.get("tree_path", "")

    if isinstance(tags, str):
        tags = [tags] if tags else []
    if isinstance(depends, str):
        depends = [depends] if depends else []

    # Field weighting: id×3, summary×2, tags×1, domain×1, date×1, body×1
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
        "tree_path": tree_path,
        "body": body,
        "path": os.path.basename(filepath),
        "searchable": searchable,
    }


# --- Index Builder ---

def build_index(base_dir=None):
    """Build BM25 inverted index from all chunks."""
    base_dir = _resolve_base_dir(base_dir)
    config = load_config(base_dir)
    k1 = config["search"]["bm25_k1"]
    b = config["search"]["bm25_b"]
    idf_floor = config["search"]["idf_floor"]

    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    if not os.path.isdir(chunks_dir):
        raise EasybaseError(f"{chunks_dir} directory not found.")

    chunk_files = sorted(f for f in os.listdir(chunks_dir) if f.endswith(".md"))
    if not chunk_files:
        raise EasybaseError("No .md files found in chunks/")

    chunks = {}
    for fname in chunk_files:
        filepath = os.path.join(chunks_dir, fname)
        chunk = parse_chunk(filepath)
        if chunk and chunk["id"]:
            chunks[chunk["id"]] = chunk

    if not chunks:
        raise EasybaseError("No valid chunks parsed.")

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

    ref_counts = defaultdict(int)
    for chunk_id, chunk in chunks.items():
        for dep in chunk["depends"]:
            dep = dep.strip()
            if dep and dep != "\u2014":
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
            "tree_path": chunk["tree_path"],
        }

    index = {
        "N": N,
        "avgdl": round(avgdl, 2),
        "k1": k1,
        "b": b,
        "idf_floor": idf_floor,
        "doc_lengths": doc_lengths,
        "ref_weights": {k: round(v, 2) for k, v in ref_weights.items()},
        "inverted": {
            term: {"df": data["df"], "postings": data["postings"]}
            for term, data in sorted(inverted.items())
        },
        "chunks": chunk_meta,
    }

    index_path = os.path.join(base_dir, INDEX_FILE)
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)

    print(f"Indexed {N} chunks, {len(inverted)} unique terms \u2192 {INDEX_FILE}")

    # On first run, generate root summary if empty
    root_summary_path = os.path.join(base_dir, KNOWLEDGE_DIR, "_summary.md")
    if os.path.exists(root_summary_path):
        with open(root_summary_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content or content == "# Knowledge Base":
            _generate_root_summary(chunks, root_summary_path)

    return index


def _generate_root_summary(chunks, summary_path):
    """Generate initial root _summary.md listing all chunks."""
    lines = ["# Knowledge Base", ""]
    lines.append("## Available Details")
    lines.append("| ID | Summary | Domain |")
    lines.append("|----|---------|--------|")
    for chunk_id in sorted(chunks.keys()):
        c = chunks[chunk_id]
        lines.append(f"| {chunk_id} | {c['summary']} | {c['domain']} |")

    parent_to_children = defaultdict(list)
    for chunk_id, c in chunks.items():
        for dep in c["depends"]:
            dep = dep.strip()
            if dep and dep != "\u2014":
                parent_to_children[dep].append(chunk_id)

    if parent_to_children:
        lines.append("")
        lines.append("## Dependencies")
        for parent in sorted(parent_to_children.keys()):
            children = sorted(parent_to_children[parent])
            lines.append(f"{parent} \u2190 {', '.join(children)}")

    lines.append("")

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Generated root summary: {summary_path}")


# --- Search ---

def load_index(base_dir=None):
    """Load the precomputed index."""
    base_dir = _resolve_base_dir(base_dir)
    index_path = os.path.join(base_dir, INDEX_FILE)
    if not os.path.exists(index_path):
        raise EasybaseError(f"Error: {INDEX_FILE} not found. Run 'python3 ctx.py index' first.")
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def search(query, index, top_k=None, scope=None, verbose=False):
    """Run modified BM25 search."""
    tokens = tokenize(query)
    if not tokens:
        return []

    N = index["N"]
    avgdl = index["avgdl"]
    k1 = index["k1"]
    b = index["b"]
    idf_floor = index.get("idf_floor", DEFAULT_IDF_FLOOR)
    inverted = index["inverted"]
    doc_lengths = index["doc_lengths"]
    ref_weights = index["ref_weights"]
    chunks_meta = index.get("chunks", {})

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
        idf = max(idf, idf_floor)

        if verbose:
            print(f"  [{token}] df={df}, idf={idf:.3f}, postings={list(postings.keys())}")

        for chunk_id, tf in postings.items():
            # Scope filter
            if scope:
                tp = chunks_meta.get(chunk_id, {}).get("tree_path", "")
                if not tp.startswith(scope):
                    continue

            dl = doc_lengths.get(chunk_id, avgdl)
            tf_sat = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            scores[chunk_id] += idf * tf_sat

    for chunk_id in scores:
        w = ref_weights.get(chunk_id, 1.0)
        scores[chunk_id] *= w

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if top_k is not None:
        ranked = ranked[:top_k]

    results = []
    for chunk_id, score in ranked:
        meta = chunks_meta.get(chunk_id, {})
        results.append({
            "id": chunk_id,
            "score": round(score, 4),
            "summary": meta.get("summary", ""),
            "path": meta.get("path", ""),
            "tree_path": meta.get("tree_path", ""),
        })

    return results


# --- CLI Commands ---

def _create_default_soul(soul_path):
    """Create a default soul.md template."""
    lines = [
        "# Soul",
        "",
        "## About Me",
        "<!-- Describe yourself: role, expertise, what you work on. -->",
        "<!-- The AI reads this first every session to understand who you are. -->",
        "",
        "## Preferences",
        "<!-- How should the AI communicate? What style do you prefer? -->",
        "<!-- Examples: concise vs detailed, formal vs casual, code-first vs explanation-first -->",
        "",
        "## Current Focus",
        "<!-- What are you currently working on? What are your priorities? -->",
        "",
        "## Notes for AI",
        "<!-- Anything the AI should always keep in mind when working with you. -->",
        "",
    ]
    with open(soul_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _create_default_permission(permission_path):
    """Create a default permission.md template."""
    lines = [
        "# Permissions",
        "",
        "This file records what the AI is allowed to do. It is loaded at the start",
        "of every session. The AI checks this before asking for permission.",
        "",
        "## Global",
        "",
        "These rules apply to ALL projects and sessions.",
        "",
        "### Allowed Directories",
        "<!-- Directories the AI can read and write in any project. -->",
        "",
        "### Read-Only Directories",
        "<!-- Directories the AI can read but must NOT modify. -->",
        "",
        "### Blocked Directories",
        "<!-- Directories the AI must never access. -->",
        "",
        "### Allowed Commands",
        "<!-- Shell commands the AI can run in any project. -->",
        "",
        "### Blocked Commands",
        "<!-- Commands the AI must never run. -->",
        "<!-- Examples: rm -rf, sudo, shutdown -->",
        "",
        "---",
        "",
        "<!-- Per-project permissions are added below by the AI when you say",
        '   "allow forever" or "always allow". Each project gets its own section. -->',
        "",
    ]
    with open(permission_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def cmd_init(base_dir=None):
    """Interactive setup — generates config.yaml and directory structure."""
    if base_dir is None:
        base_dir = os.environ.get("EASYBASE_DIR", DEFAULT_DATA_DIR)
    abs_base = os.path.abspath(base_dir)
    os.makedirs(abs_base, exist_ok=True)

    print(BANNER)
    print("  Setup")
    print("  " + "=" * 30)
    print()
    print(f"  Data directory: {abs_base}")
    print()

    # Copy PROTOCOL.md from source code to data dir
    src_protocol = os.path.join(SCRIPT_DIR, PROTOCOL_FILE)
    dst_protocol = os.path.join(abs_base, PROTOCOL_FILE)
    if os.path.exists(src_protocol):
        shutil.copy2(src_protocol, dst_protocol)

    # --- Phase 1: User Profile ---
    print("Phase 1: User Profile")
    print("-" * 30)
    print("Easybase uses a soul.md file for your general context (preferences,")
    print("background, how the AI should work with you). This is loaded first,")
    print("before any project-specific knowledge.")
    print()
    print("Do you already have a user profile file (e.g., CLAUDE.md, soul.md, .cursorrules)?")
    print("  [1] No \u2014 create a new soul.md for me")
    print("  [2] Yes \u2014 I have an existing file I want to use")
    soul_choice = input("Choice [1]: ").strip() or "1"

    soul_path = os.path.join(base_dir, SOUL_FILE)
    if soul_choice == "2":
        existing_path = input("Path to your existing file: ").strip()
        existing_path = os.path.expanduser(existing_path)
        if not os.path.exists(existing_path):
            print(f"  File not found: {existing_path}")
            print(f"  Creating a blank {SOUL_FILE} instead.")
            _create_default_soul(soul_path)
        elif os.path.isdir(existing_path):
            print(f"  {existing_path} is a directory, not a file.")
            print(f"  Creating a blank {SOUL_FILE} instead.")
            _create_default_soul(soul_path)
        else:
            with open(existing_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            with open(soul_path, 'w', encoding='utf-8') as f:
                f.write(existing_content)
            print(f"  Imported {existing_path} \u2192 {SOUL_FILE}")
    else:
        _create_default_soul(soul_path)

    # Create permission.md
    permission_path = os.path.join(base_dir, PERMISSION_FILE)
    _create_default_permission(permission_path)
    print(f"  Created {PERMISSION_FILE} (edit to set AI access rules)")

    # --- Phase 2: Storage ---
    print()
    print("Phase 2: Storage")
    print("-" * 30)
    print("What should the AI store?")
    print("  [1] Everything (recommended \u2014 search handles relevance)")
    print("  [2] AI decides what's worth keeping")
    print("  [3] Only when I explicitly ask")
    storage_choice = input("Choice [1]: ").strip() or "1"
    storage_map = {"1": "all", "2": "selective", "3": "manual"}
    storage_mode = storage_map.get(storage_choice, "all")

    print()
    print("Enforcement mode controls whether the AI must use ONLY the knowledge base")
    print("or can also use its own memory.")
    print("  [1] Off — AI can use both the knowledge base AND its own memory (default)")
    print("  [2] On — AI must use ONLY the knowledge base, cite chunks, never rely on memory")
    enforcement_choice = input("Choice [1]: ").strip() or "1"
    enforcement = enforcement_choice == "2"

    # --- Phase 3: Project Discovery ---
    print()
    print("Phase 3: Project Discovery")
    print("-" * 30)
    print("Easybase can scan directories on your machine for existing projects")
    print("by looking for AI context files (CLAUDE.md, .cursorrules, README.md, etc.).")
    print("File contents are COPIED into Easybase's data directory as searchable chunks.")
    print("Original files are never modified. You can add more projects later with: python3 ctx.py scan")
    print()
    print("Should Easybase scan for existing projects?")
    print("  [1] No \u2014 skip for now")
    print("  [2] Yes \u2014 scan for projects to import")
    scan_choice = input("Choice [1]: ").strip() or "1"

    access_mode = "sandbox"
    scan_paths = []
    imported_projects = []

    if scan_choice == "2":
        access_mode = "local-read"
        defaults = _get_default_scan_paths()
        existing = [p for p in defaults if os.path.isdir(os.path.expanduser(p))]

        print()
        if existing:
            print("Found these common directories on your machine:")
            for i, p in enumerate(existing, 1):
                print(f"  [{i}] {p}")
            print()
            print("Use these paths? (Enter to accept, or type custom paths separated by commas)")
            custom = input(f"Paths [{', '.join(existing)}]: ").strip()
            if custom:
                scan_paths = [p.strip() for p in custom.split(",") if p.strip()]
            else:
                scan_paths = existing
        else:
            print("Enter paths to scan (separated by commas):")
            custom = input("Paths: ").strip()
            scan_paths = [p.strip() for p in custom.split(",") if p.strip()]

        if scan_paths:
            print()
            print("Scanning...")
            found = _find_projects(scan_paths, max_depth=3, exclude_dir=abs_base)

            if found:
                print(f"Found {len(found)} project(s):")
                for i, proj in enumerate(found, 1):
                    files_str = ", ".join(proj["files"])
                    print(f"  [{i}] {proj['name']} \u2014 {proj['path']}")
                    print(f"      Files: {files_str}")

                print()
                print("Import which projects?")
                print("  [a] All")
                print("  [n] None")
                print("  Or enter numbers separated by commas (e.g., 1,3,5)")
                import_choice = input("Choice [a]: ").strip().lower() or "a"

                if import_choice == "n":
                    found = []
                elif import_choice != "a":
                    try:
                        indices = [int(x.strip()) - 1 for x in import_choice.split(",")]
                        found = [found[i] for i in indices if 0 <= i < len(found)]
                    except (ValueError, IndexError):
                        print("  Invalid selection, importing all.")

                imported_projects = found
            else:
                print("No projects found in the specified paths.")

    # --- Create directories and files ---
    dirs_to_create = [
        os.path.join(base_dir, CHUNKS_DIR),
        os.path.join(base_dir, KNOWLEDGE_DIR),
        os.path.join(base_dir, INBOX_DIR, "sessions"),
        os.path.join(base_dir, INBOX_DIR, "files"),
        os.path.join(base_dir, INBOX_DIR, "processed"),
        os.path.join(base_dir, LOGS_DIR),
    ]
    for d in dirs_to_create:
        os.makedirs(d, exist_ok=True)

    # Create root summary
    root_summary = os.path.join(base_dir, KNOWLEDGE_DIR, "_summary.md")
    if not os.path.exists(root_summary):
        with open(root_summary, 'w', encoding='utf-8') as f:
            f.write("# Knowledge Base\n")

    # Create empty changes log
    log_path = os.path.join(base_dir, CHANGES_LOG)
    if not os.path.exists(log_path):
        with open(log_path, 'w', encoding='utf-8') as f:
            pass

    # Generate config
    config = _default_config(
        storage_mode=storage_mode, access_mode=access_mode,
        scan_paths=scan_paths, enforcement=enforcement,
    )
    config_path = os.path.join(base_dir, CONFIG_FILE)
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(generate_yaml(config))

    # Import projects if any were selected
    if imported_projects:
        print()
        print(f"Copying project files into {abs_base}/chunks/ as searchable knowledge...")
        all_imported = _import_projects(imported_projects, base_dir)
        print(f"  Imported {len(all_imported)} chunk(s) from {len(imported_projects)} project(s).")

    log_change("INIT setup completed", base_dir)

    # --- Phase 4: AI Tool Integration ---
    print()
    print("Phase 4: Connect to your AI tool")
    print("-" * 30)

    mcp_server_path = os.path.join(SCRIPT_DIR, "mcp_server.py")

    # Check if mcp is installed
    mcp_installed = False
    try:
        import importlib
        importlib.import_module("mcp")
        mcp_installed = True
    except ImportError:
        pass

    if not mcp_installed:
        print("Installing mcp package...")
        import subprocess
        pip_cmd = [sys.executable, "-m", "pip", "install"]
        # Use --user if not in a virtual environment to avoid polluting global Python
        in_venv = (hasattr(sys, 'real_prefix') or
                   (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        if not in_venv:
            pip_cmd.append("--user")
        pip_cmd.append("mcp")
        try:
            subprocess.run(pip_cmd, capture_output=True, check=True)
            print("  mcp installed.")
            mcp_installed = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  Could not install mcp automatically.")
            print("  Please run: pip install --user mcp")

    # Detect and auto-register with Claude Code
    has_claude = shutil.which("claude") is not None
    registered = False

    if has_claude:
        print("Detected: Claude Code")
        import subprocess
        # Remove existing registration if present (re-running init should just work)
        subprocess.run(
            ["claude", "mcp", "remove", "easybase", "-s", "user"],
            capture_output=True,
        )
        print("  Registering Easybase as MCP server...")
        try:
            subprocess.run([
                "claude", "mcp", "add", "--scope", "user",
                "--transport", "stdio", "easybase",
                "-e", f"EASYBASE_DIR={abs_base}",
                "--", sys.executable, mcp_server_path,
            ], capture_output=True, check=True)
            print("  Registered. The MCP server tells Claude to load Easybase")
            print("  automatically — no CLAUDE.md needed.")
            registered = True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  Auto-registration failed: {e}")
            print(f"  Run manually:")
            print(f"    claude mcp add --scope user --transport stdio easybase \\")
            print(f"      -e EASYBASE_DIR={abs_base} \\")
            print(f"      -- python3 {mcp_server_path}")

    if not has_claude:
        print("Claude Code not detected.")
        print()
        print("For MCP apps (Claude Desktop, Cursor, Windsurf):")
        print("  Register Easybase as an MCP server. The server automatically")
        print("  instructs the AI to load Easybase — no config file changes needed.")
        print()
        print(f"  Claude Desktop (add to claude_desktop_config.json):")
        print(f'    "easybase": {{"command": "python3",')
        print(f'      "args": ["{mcp_server_path}"],')
        print(f'      "env": {{"EASYBASE_DIR": "{abs_base}"}}}}')
        print()
        print(f"  Cursor / Windsurf: same command/args/env in MCP settings.")
        print()
        print("For web AI (ChatGPT, Claude.ai, Gemini):")
        print("  Use the browser extension in the extension/ folder.")
        print("  1. Run: python3 http_server.py")
        print("  2. Load the extension in Chrome (chrome://extensions > Load unpacked)")
        print("  The extension injects context and captures responses automatically.")

    # --- Summary ---
    print()
    print("Setup complete!")
    print("=" * 40)
    if registered:
        print("Easybase is ready. Start a new Claude Code session — it will")
        print("load your knowledge base automatically.")
    print()
    print("  Edit soul.md to describe yourself and your preferences.")
    print("  Edit permission.md to set what the AI can access and run.")


def cmd_index(base_dir=None):
    """Build index from chunks."""
    base_dir = _resolve_base_dir(base_dir)
    try:
        build_index(base_dir)
    except EasybaseError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_search(args, base_dir=None):
    """Search for chunks by query."""
    base_dir = _resolve_base_dir(base_dir)
    if not args:
        print('Usage: python3 ctx.py search "query" [--top N] [--scope path] [-v]')
        sys.exit(1)

    query = args[0]
    top_k = None
    scope = None
    verbose = False

    i = 1
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top_k = int(args[i + 1])
            i += 2
        elif args[i] == "--scope" and i + 1 < len(args):
            scope = args[i + 1]
            i += 2
        elif args[i] == "-v":
            verbose = True
            i += 1
        else:
            i += 1

    index = load_index(base_dir)
    results = search(query, index, top_k=top_k, scope=scope, verbose=verbose)

    if not results:
        print("No results found.")
        return

    print(f'\nSearch: "{query}"')
    if scope:
        print(f"Scope: {scope}")
    print(f"{'Rank':<6}{'ID':<12}{'Score':<10}{'Summary'}")
    print("-" * 70)
    for rank, r in enumerate(results, 1):
        print(f"{rank:<6}{r['id']:<12}{r['score']:<10}{r['summary']}")


def _auto_capture(content, msg_type, base_dir=None):
    """Automatically capture a query or response to inbox/sessions/."""
    base_dir = _resolve_base_dir(base_dir)
    sessions_dir = os.path.join(base_dir, INBOX_DIR, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts_file}_{msg_type}.md"
    filepath = os.path.join(sessions_dir, filename)

    lines = [
        "---",
        f"type: {msg_type}",
        f"timestamp: {ts}",
        "---",
        "",
        content,
        "",
    ]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    log_change(f"CAPTURE {msg_type}:{filename}", base_dir)


def _check_project_freshness(base_dir=None):
    """Check if any imported project files have changed since import."""
    base_dir = _resolve_base_dir(base_dir)
    registry = _load_projects_registry(base_dir)
    if not registry:
        return []

    stale = []
    for path, info in registry.items():
        import_date = info.get("imported", "")
        if not import_date:
            continue
        for filename in info.get("files", []):
            filepath = os.path.join(path, filename)
            if not os.path.isfile(filepath):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d")
            if mtime > import_date:
                stale.append({
                    "project": info["name"],
                    "file": filename,
                    "modified": mtime,
                    "imported": import_date,
                })

    return stale


# --- Internal API (used by MCP and HTTP servers) ---

def _load_context(query, base_dir=None, top_k=None, scope=None):
    """Build and return the full context block as a string."""
    base_dir = _resolve_base_dir(base_dir)
    config = load_config(base_dir)

    # Auto-capture the user's query
    _auto_capture(query, "query", base_dir)

    index = load_index(base_dir)
    results = search(query, index, top_k=top_k, scope=scope)

    out = io.StringIO()

    out.write("[CONTEXT]\n")

    # Check if the AI skipped storing its answer from the previous load
    skipped_query = _check_pending_store(base_dir)
    if skipped_query:
        out.write("# !! VIOLATION: You did NOT store your last answer !!\n")
        out.write(f"Your previous query was: \"{skipped_query}\"\n")
        out.write("You answered but NEVER called easybase_add to store it.\n")
        out.write("That answer is now LOST — future sessions cannot find it.\n")
        out.write("DO NOT repeat this. After answering THIS query, you MUST call easybase_add.\n\n")

    # Set pending — cleared when easybase_add is called
    _set_pending_store(query, base_dir)

    # Always include soul.md first
    soul_path = os.path.join(base_dir, SOUL_FILE)
    if os.path.exists(soul_path):
        with open(soul_path, 'r', encoding='utf-8') as f:
            soul_content = f.read().rstrip()
        if soul_content:
            out.write(soul_content + "\n\n")

    # Include permission.md (AI access rules)
    permission_path = os.path.join(base_dir, PERMISSION_FILE)
    if os.path.exists(permission_path):
        with open(permission_path, 'r', encoding='utf-8') as f:
            permission_content = f.read().rstrip()
        if permission_content:
            out.write(permission_content + "\n\n")

    # Always include protocol — prefer code dir (stays current with git pull),
    # fall back to data dir copy
    protocol_path = os.path.join(SCRIPT_DIR, PROTOCOL_FILE)
    if not os.path.exists(protocol_path):
        protocol_path = os.path.join(base_dir, PROTOCOL_FILE)
    if os.path.exists(protocol_path):
        with open(protocol_path, 'r', encoding='utf-8') as f:
            out.write(f.read().rstrip() + "\n\n")

    # Enforcement banner
    enforcement_on = config.get("enforcement", {}).get("citation_required", False)
    if enforcement_on:
        out.write("# ENFORCEMENT MODE\n")
        out.write("You MUST use ONLY the knowledge base. Never rely on your own memory.\n")
        out.write("Do NOT reference anything from prior conversation turns.\n")
        out.write("Do NOT assume you know something \u2014 if it wasn't in the load output, search for it.\n\n")
        out.write("You MUST cite every chunk ID you used in your answer.\n")
        out.write("At the end of your response, include:\n")
        out.write("  CITED: [chunk-id-1, chunk-id-2, ...]\n")
        out.write("If no chunks were relevant: CITED: [none]\n\n")
    else:
        out.write("# Memory Policy\n")
        out.write("Use Easybase as your primary knowledge source. You may also draw on\n")
        out.write("your own knowledge when Easybase doesn't have what you need.\n")
        out.write("Always call ctx.py load first \u2014 it gives you the most relevant context.\n\n")

    # Search instruction
    out.write("# Search Instruction\n")
    out.write("After reading the retrieved chunks, check the \"All Chunks\" section below.\n")
    out.write("If any unloaded chunk looks relevant to the question, search for it:\n")
    out.write("  ctx.py search \"terms from that chunk's summary\"\n")
    out.write("Do not skip this step \u2014 it prevents missing useful information.\n\n")

    # Path summaries
    if scope:
        parts = scope.strip("/").split("/")
        for depth in range(len(parts)):
            partial = os.path.join(*parts[:depth + 1])
            summary_path = os.path.join(base_dir, KNOWLEDGE_DIR, partial, "_summary.md")
            if os.path.exists(summary_path):
                out.write(f"# Path Summary: {partial}\n")
                with open(summary_path, 'r', encoding='utf-8') as f:
                    out.write(f.read().rstrip() + "\n\n")
    else:
        root_summary = os.path.join(base_dir, KNOWLEDGE_DIR, "_summary.md")
        if os.path.exists(root_summary):
            out.write("# Root Summary\n")
            with open(root_summary, 'r', encoding='utf-8') as f:
                out.write(f.read().rstrip() + "\n\n")

    if not results:
        out.write("# Retrieved Chunks (0 results)\n")
        out.write(_format_all_chunks(index, set()))
        stale = _format_stale_projects(base_dir)
        if stale:
            out.write(stale)
        out.write(_store_reminder())
        out.write("\n[/CONTEXT]")
        return out.getvalue()

    # Load chunk bodies
    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    chunk_contents = []
    for r in results:
        filepath = os.path.join(chunks_dir, r["path"])
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            chunk_contents.append((r, content))
        else:
            chunk_contents.append((r, f"[File not found: {r['path']}]"))

    out.write(f"# Retrieved Chunks ({len(results)} results)\n")
    for r, content in chunk_contents:
        out.write(f"\n\u2500\u2500 {r['id']} | {r['summary']} | score={r['score']} \u2500\u2500\n")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                out.write(parts[2].strip() + "\n")
            else:
                out.write(content + "\n")
        else:
            out.write(content + "\n")

    # Cross-references
    out.write(f"\n# Cross-References\n")
    for r, content in chunk_contents:
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("\u2192 see:") or stripped.startswith("-> see:"):
                out.write(f"{r['id']} {stripped}\n")
                break

    out.write(_format_all_chunks(index, {r["id"] for r in results}))
    stale = _format_stale_projects(base_dir)
    if stale:
        out.write(stale)
    out.write(_store_reminder())
    out.write("\n[/CONTEXT]")
    return out.getvalue()


def _search_results(query, base_dir=None, top_k=None, scope=None):
    """Search and return list of result dicts."""
    base_dir = _resolve_base_dir(base_dir)
    index = load_index(base_dir)
    return search(query, index, top_k=top_k, scope=scope)


def _add_chunk(chunk_id, summary, body="", domain="", tags="",
               depends="", tree_path="", base_dir=None):
    """Create a chunk file, symlink, rebuild index. Returns status message."""
    base_dir = _resolve_base_dir(base_dir)
    if not chunk_id or not summary:
        raise EasybaseError("--id and --summary are required.")

    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    depends_list = [d.strip() for d in depends.split(",") if d.strip()] if depends else []
    today = datetime.now().strftime("%Y-%m-%d")

    lines = ["---"]
    lines.append(f"id: {chunk_id}")
    if domain:
        lines.append(f"domain: {domain}")
    lines.append(f"summary: {summary}")
    if tags_list:
        lines.append(f"tags: [{', '.join(tags_list)}]")
    if depends_list:
        lines.append(f"depends: [{', '.join(depends_list)}]")
    if tree_path:
        lines.append(f"tree_path: {tree_path}")
    lines.append(f"updated: {today}")
    lines.append("---")
    lines.append("")
    if body:
        lines.append(body)
    lines.append("")

    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    os.makedirs(chunks_dir, exist_ok=True)
    filepath = os.path.join(chunks_dir, f"{chunk_id}.md")

    msgs = []
    if os.path.exists(filepath):
        msgs.append(f"Warning: {filepath} already exists. Overwriting.")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    msgs.append(f"Created {filepath}")

    if tree_path:
        knowledge_dir = os.path.join(base_dir, KNOWLEDGE_DIR)
        tree_dir = os.path.join(knowledge_dir, tree_path)
        os.makedirs(tree_dir, exist_ok=True)

        link_path = os.path.join(tree_dir, f"{chunk_id}.md")
        chunk_abs = os.path.abspath(filepath)
        link_abs = os.path.abspath(link_path)
        rel_target = os.path.relpath(chunk_abs, os.path.dirname(link_abs))

        if os.path.exists(link_path) or os.path.islink(link_path):
            os.remove(link_path)
        os.symlink(rel_target, link_path)
        msgs.append(f"Linked {link_path} \u2192 {rel_target}")

    tree_info = f" tree:{tree_path}" if tree_path else ""
    log_change(f'ADD {chunk_id} "{summary}"{tree_info}', base_dir)

    # Clear the pending store flag — the AI fulfilled its obligation
    _clear_pending_store(base_dir)

    # Capture index output
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        build_index(base_dir)
    except EasybaseError as e:
        sys.stdout = old_stdout
        msgs.append(f"Index warning: {e}")
        return "\n".join(msgs)
    index_output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    msgs.append(index_output.strip())

    return "\n".join(msgs)


def _record_response(content, base_dir=None):
    """Record AI response with enforcement check. Returns status message."""
    base_dir = _resolve_base_dir(base_dir)
    if not content or not content.strip():
        raise EasybaseError("No content to record.")

    config = load_config(base_dir)
    enforcement_on = config.get("enforcement", {}).get("citation_required", False)
    cited_ids = []

    if enforcement_on:
        match = re.search(r'CITED:\s*\[([^\]]*)\]', content)
        if not match:
            raise EasybaseError(
                "Enforcement mode is on. Response must contain CITED: [chunk-id, ...]\n"
                "The AI must cite which chunks it used. See the protocol for format."
            )
        raw = match.group(1).strip()
        if raw and raw.lower() != "none":
            cited_ids = [c.strip() for c in raw.split(",") if c.strip()]

    sessions_dir = os.path.join(base_dir, INBOX_DIR, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ts_file = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts_file}_response.md"
    filepath = os.path.join(sessions_dir, filename)

    file_lines = ["---", "type: response", f"timestamp: {ts}"]
    if cited_ids:
        file_lines.append(f"cited: [{', '.join(cited_ids)}]")
    file_lines.extend(["---", "", content, ""])

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(file_lines))

    log_change(f"CAPTURE response:{filename}", base_dir)

    if cited_ids:
        return f"Response recorded. Cited: {', '.join(cited_ids)}"
    return "Response recorded."


def _rebuild_index(base_dir=None):
    """Rebuild index and return status message."""
    base_dir = _resolve_base_dir(base_dir)
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        build_index(base_dir)
    except EasybaseError:
        pass
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    return output.strip()


def _get_stats(base_dir=None):
    """Return stats as a string."""
    base_dir = _resolve_base_dir(base_dir)
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

    idf_floor = index.get("idf_floor", DEFAULT_IDF_FLOOR)

    def compute_idf(df):
        return max(math.log((N - df + 0.5) / (df + 0.5) + 1), idf_floor)

    knowledge_dir = os.path.join(base_dir, KNOWLEDGE_DIR)
    tree_depth = 0
    summary_count = 0
    max_summary_tokens = 0
    max_summary_path = ""

    if os.path.isdir(knowledge_dir):
        for root, dirs, files in os.walk(knowledge_dir):
            rel = os.path.relpath(root, knowledge_dir)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > tree_depth:
                tree_depth = depth
            for fname in files:
                if fname == "_summary.md":
                    summary_count += 1
                    fpath = os.path.join(root, fname)
                    with open(fpath, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    est_tokens = len(file_content) // 4
                    if est_tokens > max_summary_tokens:
                        max_summary_tokens = est_tokens
                        max_summary_path = os.path.relpath(fpath, base_dir)

    out = io.StringIO()
    out.write("=== Easybase Index Stats ===\n")
    out.write(f"Chunks (N):          {N}\n")
    out.write(f"Unique terms:        {unique_terms}\n")
    out.write(f"Avg doc length:      {avgdl:.1f} tokens\n")
    out.write(f"Avg posting length:  {avg_posting:.2f}\n")
    out.write(f'Max posting list:    "{max_entry[0]}" (df={max_entry[1]["df"]})\n')
    out.write(f"Terms with df=1:     {df1_count}\n")
    out.write(f"\nTree depth:          {tree_depth}\n")
    out.write(f"Summary files:       {summary_count}\n")
    if max_summary_path:
        out.write(f"Largest summary:     {max_summary_path} (~{max_summary_tokens} tokens)\n")
    out.write("\nTop-5 highest df terms:\n")
    for term, entry in sorted_by_df_desc:
        out.write(f"  {term:<20} df={entry['df']:<4} idf={compute_idf(entry['df']):.3f}\n")
    out.write("\nBottom-3 lowest df terms:\n")
    for term, entry in sorted_by_df_asc:
        out.write(f"  {term:<20} df={entry['df']:<4} idf={compute_idf(entry['df']):.3f}\n")

    return out.getvalue().rstrip()


def _ingest_files(base_dir=None):
    """Process inbox files and return their contents as a string."""
    base_dir = _resolve_base_dir(base_dir)
    inbox_sessions = os.path.join(base_dir, INBOX_DIR, "sessions")
    inbox_files = os.path.join(base_dir, INBOX_DIR, "files")
    processed_dir = os.path.join(base_dir, INBOX_DIR, "processed")
    os.makedirs(processed_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = io.StringIO()
    found = False

    if os.path.isdir(inbox_sessions):
        for fname in sorted(os.listdir(inbox_sessions)):
            fpath = os.path.join(inbox_sessions, fname)
            if not os.path.isfile(fpath):
                continue
            found = True
            out.write(f"\n{'='*60}\n")
            out.write(f"SESSION LOG: {fname}\n")
            out.write(f"{'='*60}\n")
            with open(fpath, 'r', encoding='utf-8') as f:
                out.write(f.read())
            dest = os.path.join(processed_dir, f"{timestamp}_{fname}")
            shutil.move(fpath, dest)
            out.write(f"\n[Moved to processed/]\n")
            log_change(f"INGEST session:{fname}", base_dir)

    if os.path.isdir(inbox_files):
        for fname in sorted(os.listdir(inbox_files)):
            fpath = os.path.join(inbox_files, fname)
            if not os.path.isfile(fpath):
                continue
            found = True
            out.write(f"\n{'='*60}\n")
            out.write(f"FILE: {fname}\n")
            out.write(f"{'='*60}\n")
            with open(fpath, 'r', encoding='utf-8') as f:
                out.write(f.read())
            dest = os.path.join(processed_dir, f"{timestamp}_{fname}")
            shutil.move(fpath, dest)
            out.write(f"\n[Moved to processed/]\n")
            log_change(f"INGEST file:{fname}", base_dir)

    if not found:
        return "No files to process in inbox/."
    return out.getvalue()


def _scan_projects(paths=None, base_dir=None):
    """Scan for projects and import all new ones. Returns status message."""
    base_dir = _resolve_base_dir(base_dir)
    abs_base = os.path.abspath(base_dir)
    config = load_config(base_dir)

    scan_paths = paths if paths else config.get("scan", {}).get("paths", [])
    max_depth = config.get("scan", {}).get("max_depth", 3)

    if not scan_paths:
        raise EasybaseError("No scan paths configured. Set scan paths in config.yaml.")

    found = _find_projects(scan_paths, max_depth=max_depth, exclude_dir=abs_base)
    registry = _load_projects_registry(base_dir)
    new_projects = [p for p in found if p["path"] not in registry]

    if not new_projects:
        return f"Found {len(found)} project(s), all already imported."

    all_imported = _import_projects(new_projects, base_dir)
    lines = [f"Imported {len(all_imported)} chunk(s) from {len(new_projects)} new project(s):"]
    for proj in new_projects:
        lines.append(f"  - {proj['name']} ({', '.join(proj['files'])})")
    return "\n".join(lines)


def _add_permission(project, permission_type, value, base_dir=None):
    """Add a permanent permission for a project (or global).

    Args:
        project: Project name, or "global" for global permissions
        permission_type: One of "allow_dir", "readonly_dir", "block_dir",
                         "allow_cmd", "block_cmd"
        value: The directory path or command to permit/block
        base_dir: Base directory for Easybase data
    Returns:
        Confirmation message string
    """
    base_dir = _resolve_base_dir(base_dir)
    permission_path = os.path.join(base_dir, PERMISSION_FILE)
    if not os.path.exists(permission_path):
        _create_default_permission(permission_path)

    with open(permission_path, 'r', encoding='utf-8') as f:
        content = f.read()

    value = value.strip()
    if not value:
        raise EasybaseError("Permission value cannot be empty.")

    valid_types = {
        "allow_dir": "Allowed Directories",
        "readonly_dir": "Read-Only Directories",
        "block_dir": "Blocked Directories",
        "allow_cmd": "Allowed Commands",
        "block_cmd": "Blocked Commands",
    }
    if permission_type not in valid_types:
        raise EasybaseError(f"Invalid permission type: {permission_type}. "
                            f"Must be one of: {', '.join(valid_types.keys())}")

    section_heading = valid_types[permission_type]
    entry_line = f"- {value}"
    is_global = project.lower() == "global"

    if is_global:
        # Insert into the Global section under the right heading
        # Find "### {section_heading}" under "## Global"
        target = f"### {section_heading}"
        pos = content.find("## Global")
        if pos == -1:
            raise EasybaseError("Cannot find ## Global section in permission.md")

        heading_pos = content.find(target, pos)
        if heading_pos == -1:
            raise EasybaseError(f"Cannot find {target} section in permission.md")

        # Check if this value already exists
        if entry_line in content:
            return f"Permission already exists: {value}"

        # Find the end of this section (next ### or ## or ---)
        after_heading = heading_pos + len(target)
        next_section = len(content)
        for marker in ["###", "##", "---"]:
            idx = content.find(marker, after_heading + 1)
            if idx != -1 and idx < next_section:
                next_section = idx

        # Insert the entry before the next section
        insert_pos = next_section
        # Back up past blank lines
        while insert_pos > 0 and content[insert_pos - 1] == '\n':
            insert_pos -= 1

        content = content[:insert_pos] + f"\n{entry_line}\n" + content[insert_pos:]

    else:
        # Per-project section
        project_header = f"## Project: {project}"

        if project_header in content:
            # Project section exists — find the right sub-section
            proj_pos = content.find(project_header)
            target = f"### {section_heading}"
            sub_pos = content.find(target, proj_pos)

            # Find the boundary of this project section (next ## Project: or end)
            next_proj = content.find("\n## Project:", proj_pos + len(project_header))
            proj_end = next_proj if next_proj != -1 else len(content)

            if sub_pos != -1 and sub_pos < proj_end:
                # Sub-section exists
                if entry_line in content[sub_pos:proj_end]:
                    return f"Permission already exists for {project}: {value}"

                after_sub = sub_pos + len(target)
                next_sub = proj_end
                for marker in ["###", "##"]:
                    idx = content.find(marker, after_sub + 1)
                    if idx != -1 and idx < next_sub:
                        next_sub = idx

                insert_pos = next_sub
                while insert_pos > 0 and content[insert_pos - 1] == '\n':
                    insert_pos -= 1
                content = content[:insert_pos] + f"\n{entry_line}\n" + content[insert_pos:]
            else:
                # Sub-section doesn't exist — add it before proj_end
                insert_pos = proj_end
                while insert_pos > 0 and content[insert_pos - 1] == '\n':
                    insert_pos -= 1
                content = content[:insert_pos] + f"\n\n### {section_heading}\n{entry_line}\n" + content[insert_pos:]
        else:
            # Project section doesn't exist — append it
            content = content.rstrip() + f"\n\n{project_header}\n\n### {section_heading}\n{entry_line}\n"

    with open(permission_path, 'w', encoding='utf-8') as f:
        f.write(content)

    scope = project if not is_global else "global"
    log_change(f"PERMIT {scope}: {permission_type} = {value}", base_dir)
    return f"Recorded permanent permission for {scope}: {section_heading} \u2014 {value}"


def _check_integrity(base_dir=None):
    """Validate system integrity and return report string."""
    base_dir = _resolve_base_dir(base_dir)
    issues = []

    config_path = os.path.join(base_dir, CONFIG_FILE)
    if not os.path.exists(config_path):
        issues.append("WARNING: config.yaml not found.")
    else:
        try:
            load_config(base_dir)
        except Exception as e:
            issues.append(f"ERROR: config.yaml is invalid: {e}")

    chunks_dir = os.path.join(base_dir, CHUNKS_DIR)
    index_path = os.path.join(base_dir, INDEX_FILE)

    chunk_files = set()
    if os.path.isdir(chunks_dir):
        chunk_files = {f for f in os.listdir(chunks_dir) if f.endswith(".md")}

    if not os.path.exists(index_path):
        if chunk_files:
            issues.append("WARNING: index.json not found but chunks exist. Run index to fix.")
    else:
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)
        indexed_chunks = set(index.get("chunks", {}).keys())
        for fname in sorted(chunk_files):
            filepath = os.path.join(chunks_dir, fname)
            chunk = parse_chunk(filepath)
            if chunk is None:
                issues.append(f"ERROR: {fname} has invalid frontmatter")
            elif not chunk["id"]:
                issues.append(f"ERROR: {fname} missing 'id' field")
            elif not chunk["summary"]:
                issues.append(f"WARNING: {fname} missing 'summary' field")

        actual_ids = set()
        for fname in chunk_files:
            c = parse_chunk(os.path.join(chunks_dir, fname))
            if c and c["id"]:
                actual_ids.add(c["id"])

        stale = indexed_chunks - actual_ids
        missing = actual_ids - indexed_chunks
        if stale:
            issues.append(f"WARNING: Index contains chunks not on disk: {', '.join(sorted(stale))}")
        if missing:
            issues.append(f"WARNING: Chunks on disk not in index: {', '.join(sorted(missing))}. Run index to fix.")

    all_ids = set()
    all_depends = defaultdict(list)
    if os.path.isdir(chunks_dir):
        for fname in sorted(chunk_files):
            c = parse_chunk(os.path.join(chunks_dir, fname))
            if c and c["id"]:
                all_ids.add(c["id"])
                for dep in c["depends"]:
                    dep = dep.strip()
                    if dep and dep != "\u2014":
                        all_depends[c["id"]].append(dep)

    for chunk_id, deps in all_depends.items():
        for dep in deps:
            if dep not in all_ids:
                issues.append(f"WARNING: {chunk_id} depends on '{dep}' which does not exist")

    knowledge_dir = os.path.join(base_dir, KNOWLEDGE_DIR)
    if os.path.isdir(knowledge_dir):
        for root, dirs, files in os.walk(knowledge_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                if os.path.islink(fpath):
                    target = os.path.realpath(fpath)
                    if not os.path.exists(target):
                        rel = os.path.relpath(fpath, base_dir)
                        issues.append(f"ERROR: Broken symlink: {rel}")
                if fname == "_summary.md":
                    with open(fpath, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    if not content:
                        rel = os.path.relpath(fpath, base_dir)
                        issues.append(f"WARNING: Empty summary: {rel}")

    soul_path = os.path.join(base_dir, SOUL_FILE)
    if not os.path.exists(soul_path):
        issues.append("WARNING: soul.md not found.")

    permission_path = os.path.join(base_dir, PERMISSION_FILE)
    if not os.path.exists(permission_path):
        issues.append("WARNING: permission.md not found.")

    protocol_path = os.path.join(SCRIPT_DIR, PROTOCOL_FILE)
    if not os.path.exists(protocol_path):
        protocol_path = os.path.join(base_dir, PROTOCOL_FILE)
        if not os.path.exists(protocol_path):
            issues.append("WARNING: PROTOCOL.md not found")

    if issues:
        return "\n".join(issues) + f"\n\n{len(issues)} issue(s) found."
    return "All checks passed."


# --- CLI Commands (thin wrappers) ---

def cmd_load(args, base_dir=None):
    """Search + display full context block with protocol."""
    base_dir = _resolve_base_dir(base_dir)
    if not args:
        print('Usage: python3 ctx.py load "query" [--top N] [--scope path]')
        sys.exit(1)

    query = args[0]
    top_k = None
    scope = None

    i = 1
    while i < len(args):
        if args[i] == "--top" and i + 1 < len(args):
            top_k = int(args[i + 1])
            i += 2
        elif args[i] == "--scope" and i + 1 < len(args):
            scope = args[i + 1]
            i += 2
        else:
            i += 1

    print(_load_context(query, base_dir, top_k, scope))


def _format_all_chunks(index, matched_ids):
    """Format full inventory of all chunks for systemic error prevention."""
    chunks_meta = index.get("chunks", {})
    if not chunks_meta:
        return ""
    lines = ["\n# All Chunks"]
    lines.append("If you need information not covered above, search for these:")
    for cid in sorted(chunks_meta.keys()):
        marker = "  *" if cid in matched_ids else "   "
        summary = chunks_meta[cid].get("summary", "")
        lines.append(f"{marker} {cid} \u2014 {summary}")
    return "\n".join(lines)


def _format_stale_projects(base_dir=None):
    """Format stale project warnings if any."""
    base_dir = _resolve_base_dir(base_dir)
    stale = _check_project_freshness(base_dir)
    if not stale:
        return ""
    lines = ["\n# Stale Projects"]
    lines.append("The following imported projects have changed since import:")
    for s in stale:
        lines.append(f"  - {s['project']} ({s['file']} modified {s['modified']}, imported {s['imported']})")
    lines.append("Run `ctx.py scan` to re-import.")
    return "\n".join(lines)


def cmd_add(args, base_dir=None):
    """Add a new chunk file and rebuild index."""
    base_dir = _resolve_base_dir(base_dir)
    chunk_id = ""
    summary = ""
    body = ""
    domain = ""
    tags = ""
    depends = ""
    tree_path = ""

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
        elif args[i] == "--tree-path" and i + 1 < len(args):
            tree_path = args[i + 1]
            i += 2
        else:
            i += 1

    if not chunk_id or not summary:
        print('Usage: python3 ctx.py add --id ID --summary "..." --body "..."')
        print('  [--domain DOMAIN] [--tags "t1,t2"] [--depends "id1,id2"]')
        print('  [--tree-path "path/to/branch"]')
        sys.exit(1)

    try:
        result = _add_chunk(chunk_id, summary, body, domain, tags, depends, tree_path, base_dir)
        print(result)
    except EasybaseError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_ingest(base_dir=None):
    """Process files in inbox/ for AI review."""
    base_dir = _resolve_base_dir(base_dir)
    print(_ingest_files(base_dir))


def cmd_stats(base_dir=None):
    """Show index and tree statistics."""
    base_dir = _resolve_base_dir(base_dir)
    print(_get_stats(base_dir))


def cmd_check(base_dir=None):
    """Validate system integrity."""
    base_dir = _resolve_base_dir(base_dir)
    result = _check_integrity(base_dir)
    print(result)
    if "issue(s) found" in result:
        sys.exit(1)


def cmd_permit(args, base_dir=None):
    """Record a permanent permission."""
    base_dir = _resolve_base_dir(base_dir)
    if not args or len(args) < 3:
        print('Usage: python3 ctx.py permit --project "name" --type allow_dir --value "/path"')
        print('       python3 ctx.py permit --project global --type allow_cmd --value "git"')
        print()
        print("Types: allow_dir, readonly_dir, block_dir, allow_cmd, block_cmd")
        sys.exit(1)

    project = None
    perm_type = None
    value = None

    i = 0
    while i < len(args):
        if args[i] == "--project" and i + 1 < len(args):
            project = args[i + 1]
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            perm_type = args[i + 1]
            i += 2
        elif args[i] == "--value" and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        else:
            i += 1

    if not project or not perm_type or not value:
        print("Error: --project, --type, and --value are all required.")
        sys.exit(1)

    try:
        result = _add_permission(project, perm_type, value, base_dir)
        print(result)
    except EasybaseError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_record(args, base_dir=None):
    """Record session content into inbox for later processing."""
    base_dir = _resolve_base_dir(base_dir)
    content = None

    i = 0
    while i < len(args):
        if args[i] == "--content" and i + 1 < len(args):
            content = args[i + 1]
            i += 2
        elif args[i] == "--file" and i + 1 < len(args):
            filepath = os.path.expanduser(args[i + 1])
            if not os.path.isfile(filepath):
                print(f"Error: File not found: {filepath}")
                sys.exit(1)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            i += 2
        else:
            i += 1

    # Read from stdin if no content or file provided
    if content is None:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            print('Usage: python3 ctx.py record --content "session text"')
            print('       python3 ctx.py record --file /path/to/session.log')
            print('       echo "text" | python3 ctx.py record')
            sys.exit(1)

    if not content.strip():
        print("Error: No content to record.")
        sys.exit(1)

    sessions_dir = os.path.join(base_dir, INBOX_DIR, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.md"
    filepath = os.path.join(sessions_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    log_change(f"RECORD session:{filename}", base_dir)
    print(f"Recorded session: {filepath}")


def cmd_respond(args, base_dir=None):
    """Record AI response — called after answering the user."""
    base_dir = _resolve_base_dir(base_dir)
    content = None

    i = 0
    while i < len(args):
        if args[i] == "--file" and i + 1 < len(args):
            filepath = os.path.expanduser(args[i + 1])
            if not os.path.isfile(filepath):
                print(f"Error: File not found: {filepath}")
                sys.exit(1)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            i += 2
        else:
            if content is None:
                content = args[i]
            i += 1

    if content is None:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            print('Usage: python3 ctx.py respond "AI response text"')
            print('       python3 ctx.py respond --file /path/to/response.txt')
            print('       echo "response" | python3 ctx.py respond')
            sys.exit(1)

    try:
        result = _record_response(content, base_dir)
        print(result)
    except EasybaseError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_scan(args, base_dir=None):
    """Re-scan for projects after initial setup."""
    base_dir = _resolve_base_dir(base_dir)
    abs_base = os.path.abspath(base_dir)
    config = load_config(base_dir)

    # Get scan paths from args or config
    scan_paths = config.get("scan", {}).get("paths", [])
    max_depth = config.get("scan", {}).get("max_depth", 3)

    i = 0
    while i < len(args):
        if args[i] == "--paths" and i + 1 < len(args):
            scan_paths = [p.strip() for p in args[i + 1].split(",") if p.strip()]
            i += 2
        else:
            i += 1

    if not scan_paths:
        print("No scan paths configured. Run 'python3 ctx.py init' with project scanning,")
        print("or use: python3 ctx.py scan --paths \"~/code,~/projects\"")
        sys.exit(1)

    print(f"Scanning: {', '.join(scan_paths)}")
    found = _find_projects(scan_paths, max_depth=max_depth, exclude_dir=abs_base)

    # Filter out already-imported projects
    registry = _load_projects_registry(base_dir)
    new_projects = [p for p in found if p["path"] not in registry]

    if not new_projects:
        print(f"Found {len(found)} project(s), all already imported.")
        return

    print(f"Found {len(new_projects)} new project(s):")
    for i_proj, proj in enumerate(new_projects, 1):
        files_str = ", ".join(proj["files"])
        print(f"  [{i_proj}] {proj['name']} \u2014 {proj['path']}")
        print(f"      Files: {files_str}")

    print()
    print("Import which projects? (file contents will be COPIED into Easybase)")
    print("  [a] All")
    print("  [n] None")
    print("  Or enter numbers separated by commas (e.g., 1,3,5)")
    import_choice = input("Choice [a]: ").strip().lower() or "a"

    if import_choice == "n":
        print("No projects imported.")
        return
    elif import_choice != "a":
        try:
            indices = [int(x.strip()) - 1 for x in import_choice.split(",")]
            new_projects = [new_projects[idx] for idx in indices if 0 <= idx < len(new_projects)]
        except (ValueError, IndexError):
            print("  Invalid selection, importing all.")

    print(f"Copying project files into {abs_base}/chunks/ as searchable knowledge...")
    all_imported = _import_projects(new_projects, base_dir)
    print(f"Imported {len(all_imported)} chunk(s) from {len(new_projects)} project(s).")


def cmd_update():
    """Update Easybase to the latest version."""
    print(BANNER)
    print("  Update Easybase")
    print()

    import subprocess

    # Step 1: git pull in the code directory
    git_dir = os.path.join(SCRIPT_DIR, ".git")
    if not os.path.isdir(git_dir):
        print("Error: Not a git repository. Re-clone from GitHub to enable updates:")
        print("  git clone https://github.com/superyicheng/Easybase.git")
        sys.exit(1)

    print("1. Pulling latest code...")
    try:
        # Detect the default branch name (main or master)
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=SCRIPT_DIR, capture_output=True, text=True, check=True,
        )
        branch = result.stdout.strip()

        # Fetch latest from remote
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=SCRIPT_DIR, capture_output=True, text=True, check=True,
        )

        # Check if already up to date
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=SCRIPT_DIR, capture_output=True, text=True, check=True,
        ).stdout.strip()
        remote = subprocess.run(
            ["git", "rev-parse", f"origin/{branch}"],
            cwd=SCRIPT_DIR, capture_output=True, text=True, check=True,
        ).stdout.strip()

        if local == remote:
            print("   Already up to date.")
        else:
            # Reset to match remote — safe because user data is in ~/.easybase, not here
            subprocess.run(
                ["git", "reset", "--hard", f"origin/{branch}"],
                cwd=SCRIPT_DIR, capture_output=True, text=True, check=True,
            )
            # Clean untracked files that might conflict (e.g. new files in the repo)
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=SCRIPT_DIR, capture_output=True, text=True,
            )
            print("   Updated to latest version.")
    except subprocess.CalledProcessError as e:
        print(f"   Update failed: {e.stderr.strip() if e.stderr else e}")
        sys.exit(1)
    except FileNotFoundError:
        print("   git not found. Please install git or update manually.")
        sys.exit(1)

    # Step 2: Ensure pip dependencies are installed
    print("2. Checking dependencies...")
    try:
        import importlib
        importlib.import_module("mcp")
        print("   mcp package: installed.")
    except ImportError:
        print("   Installing mcp package...")
        pip_cmd = [sys.executable, "-m", "pip", "install"]
        in_venv = (hasattr(sys, 'real_prefix') or
                   (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        if not in_venv:
            pip_cmd.append("--user")
        pip_cmd.append("mcp")
        try:
            subprocess.run(pip_cmd, capture_output=True, check=True)
            print("   mcp installed.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("   Could not install mcp. Run manually: pip install --user mcp")

    # Step 3: Re-register MCP server if Claude Code is available
    print("3. Checking MCP registration...")
    has_claude = shutil.which("claude") is not None
    if has_claude:
        base_dir = _resolve_base_dir()
        abs_base = os.path.abspath(base_dir)
        mcp_server_path = os.path.join(SCRIPT_DIR, "mcp_server.py")
        # Remove and re-add to update paths
        subprocess.run(
            ["claude", "mcp", "remove", "easybase", "-s", "user"],
            capture_output=True,
        )
        try:
            subprocess.run([
                "claude", "mcp", "add", "--scope", "user",
                "--transport", "stdio", "easybase",
                "-e", f"EASYBASE_DIR={abs_base}",
                "--", sys.executable, mcp_server_path,
            ], capture_output=True, check=True)
            print("   MCP server re-registered.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("   MCP re-registration failed. Run init to fix.")
    else:
        print("   Claude Code not detected, skipping MCP.")

    # Step 4: Copy updated PROTOCOL.md to data dir
    print("4. Updating protocol in data directory...")
    base_dir = _resolve_base_dir()
    src_protocol = os.path.join(SCRIPT_DIR, PROTOCOL_FILE)
    dst_protocol = os.path.join(base_dir, PROTOCOL_FILE)
    if os.path.exists(src_protocol) and os.path.isdir(base_dir):
        shutil.copy2(src_protocol, dst_protocol)
        print("   PROTOCOL.md updated.")
    else:
        print("   Skipped (data directory not initialized yet).")

    print()
    print("Update complete. Start a new AI session to use the latest version.")


# --- Main ---

def main():
    if len(sys.argv) < 2:
        print(BANNER)
        print("  BM25-based context management for AI")
        print()
        print("Commands:")
        print("  init                               Interactive setup")
        print("  update                             Update Easybase to latest version")
        print('  index                              Build index from chunks/')
        print('  search "query" [--top N] [-v]      Search for chunks')
        print('         [--scope path]')
        print('  load "query" [--top N]             Search + full context block')
        print('       [--scope path]')
        print('  add --id ID --summary "..."         Add a new chunk')
        print('      [--tree-path "path"]')
        print("  ingest                             Process inbox/ files")
        print('  record --content "text"            Record a session')
        print('  respond "AI answer"                Record AI response')
        print("  scan [--paths ...]                 Re-scan for projects")
        print("  stats                              Show index statistics")
        print("  check                              Validate system integrity")
        print()
        print("Enforcement mode (configurable during init or in config.yaml):")
        print("  Off (default): AI can use knowledge base + own memory")
        print("  On: AI must cite chunks, cannot use own memory")
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "init":
        cmd_init()
    elif cmd == "update":
        cmd_update()
    elif cmd == "index":
        cmd_index()
    elif cmd == "search":
        cmd_search(args)
    elif cmd == "load":
        cmd_load(args)
    elif cmd == "add":
        cmd_add(args)
    elif cmd == "ingest":
        cmd_ingest()
    elif cmd == "record":
        cmd_record(args)
    elif cmd == "respond":
        cmd_respond(args)
    elif cmd == "scan":
        cmd_scan(args)
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "check":
        cmd_check()
    elif cmd == "permit":
        cmd_permit(args)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except EasybaseError as e:
        print(str(e))
        sys.exit(1)
