#!/usr/bin/env python3
# scripts/seed_kb.py
"""
seed_kb.py — one-shot project codebase indexer for SP2 Knowledge Base.

Usage:
    python scripts/seed_kb.py                          # all active projects with local_path
    python scripts/seed_kb.py --projects ama-solutions # specific projects by slug
    python scripts/seed_kb.py --dry-run               # print what would be indexed

Spec: docs/superpowers/specs/2026-04-26-sp2-knowledge-base-design.md §6
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Bootstrap path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", "postgresql://cruz:cruz@localhost:5432/cruz_db"))

PRIORITY_FILENAMES = {
    "README.md", "CLAUDE.md", ".env.example", "package.json",
    "requirements.txt", "pyproject.toml", "docker-compose.yml",
    "alembic.ini", "main.py", "app.py", "server.ts",
}
PRIORITY_SUFFIXES = {".sql", ".prisma"}
PRIORITY_ENTRY_PATTERNS = {"src/index.ts", "backend/api/main.py"}

SKIP_DIRS  = {"node_modules", ".git", "__pycache__", "dist", "build", ".next", "venv", ".venv"}
SKIP_EXTS  = {".lock", ".min.js", ".min.css", ".pyc", ".map", ".bin", ".whl"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"}

# Rough tokens-per-character ratio for all-MiniLM-L6-v2 context
_CHARS_PER_TOKEN = 4


def should_skip(path: Path) -> bool:
    """Return True if this file/directory should be excluded from indexing."""
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    if path.name in SKIP_NAMES:
        return True
    if path.suffix in SKIP_EXTS:
        return True
    return False


def get_priority_files(root: Path) -> List[Path]:
    """Return the list of files worth indexing from a project root."""
    result: List[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        rel = path.relative_to(root)
        # Priority: exact filename match
        if path.name in PRIORITY_FILENAMES:
            result.insert(0, path)
            continue
        # Priority: suffix match
        if path.suffix in PRIORITY_SUFFIXES:
            result.append(path)
            continue
        # Priority: entry-point patterns
        if str(rel) in PRIORITY_ENTRY_PATTERNS:
            result.append(path)
    return result


def chunk_file(content: str, max_tokens: int = 500) -> List[str]:
    """Split content into chunks of at most max_tokens tokens, splitting on blank lines."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(content) <= max_chars:
        return [content]

    paragraphs = content.split("\n\n")
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for i in range(0, len(para), max_chars):
                chunks.append(para[i:i + max_chars])
            continue
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


async def seed_project(project: dict, kb, dry_run: bool = False) -> int:
    """Index one project. Returns number of documents written."""
    local_path = project.get("local_path")
    if not local_path:
        print(f"  SKIP {project['name']}: local_path not set")
        return 0

    root = Path(local_path)
    if not root.exists():
        print(f"  SKIP {project['name']}: local_path {local_path} does not exist")
        return 0

    files = get_priority_files(root)
    doc_count = 0
    t0 = time.monotonic()

    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"    WARN: could not read {fpath}: {e}")
            continue

        rel_path = str(fpath.relative_to(root))
        doc_type = "readme" if fpath.name in {"README.md", "CLAUDE.md"} else "file_summary"
        chunks = chunk_file(content)

        for idx, chunk in enumerate(chunks):
            if dry_run:
                print(f"    [dry-run] {rel_path} chunk {idx} ({len(chunk)} chars)")
            else:
                await kb.write_project_doc(
                    project_id=project["id"],
                    project_name=project["name"],
                    content=chunk,
                    doc_type=doc_type,
                    file_path=rel_path,
                    chunk_index=idx,
                )
            doc_count += 1

    elapsed = time.monotonic() - t0
    print(f"  {project['name']}: indexed {doc_count} docs ({len(files)} files) in {elapsed:.1f}s")
    return doc_count


async def main(project_slugs: Optional[List[str]] = None, dry_run: bool = False) -> None:
    from services.db import get_db_service
    from services.knowledge_base import get_kb_service

    db = get_db_service()
    await db.connect()
    kb = get_kb_service()

    query = "SELECT id, name, slug, local_path FROM projects WHERE status = 'active'"
    params: list = []
    if project_slugs:
        placeholders = ", ".join(f"${i+1}" for i in range(len(project_slugs)))
        query += f" AND slug IN ({placeholders})"
        params = project_slugs

    projects = await db.fetch(query, *params)
    if not projects:
        print("No matching active projects found.")
        return

    total = 0
    for project in projects:
        total += await seed_project(dict(project), kb, dry_run=dry_run)

    await db.disconnect()
    print(f"\nDone. Total documents indexed: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the CRUZ knowledge base")
    parser.add_argument("--projects", nargs="*", help="Project slugs to seed")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()
    asyncio.run(main(project_slugs=args.projects, dry_run=args.dry_run))
