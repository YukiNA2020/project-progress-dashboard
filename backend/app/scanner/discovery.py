"""Read-only discovery of Markdown files under a registered project path.

Rules enforced here:

* Only the folder the user registered is walked; no parent, sibling, or
  user-profile traversal.
* Dependency, build, VCS, cache, and hidden directories are pruned.
* Files are opened read-only and never written, renamed, or deleted.
* Symlinked directories are not followed, and symlinked files are only read
  when their target still resolves inside the registered folder.

The scanner never uses file modification times. ``st_mtime`` is not read at
all, so it cannot leak into a status decision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "node_modules",
    "bower_components",
    "dist",
    "build",
    "out",
    "target",
    "bin",
    "obj",
    "coverage",
    "vendor",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "site-packages",
    ".next",
    ".nuxt",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".gradle",
    ".terraform",
    "Pods",
    "DerivedData",
    # Sample and fixture folders hold demo documents, not project progress.
    "fixtures",
    "__fixtures__",
    "testdata",
    "test-data",
    "snapshots",
    "samples",
}

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd"}

PRIORITY_FILENAMES = (
    "readme.md",
    "status.md",
    "progress.md",
    "roadmap.md",
    "plan.md",
    "testing.md",
    "changelog.md",
    "notes.md",
    "todo.md",
    "tasks.md",
)

MAX_FILES = 300
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024

ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "latin-1")


@dataclass
class MarkdownFile:
    relative_path: str
    absolute_path: Path
    text: str
    encoding: str


@dataclass
class Discovery:
    files: List[MarkdownFile] = field(default_factory=list)
    skipped_directories: int = 0
    skipped_files: int = 0
    skipped_large: int = 0
    truncated: bool = False
    unreadable: List[str] = field(default_factory=list)
    encodings: Dict[str, int] = field(default_factory=dict)


def resolve_project_root(folder_path: str) -> Tuple[Optional[Path], Optional[str]]:
    """Return the folder to scan, or a reason why it cannot be scanned."""
    if not folder_path or not folder_path.strip():
        return None, "path_empty"
    raw = Path(folder_path).expanduser()
    if not raw.exists():
        return None, "path_not_found"
    if not raw.is_dir():
        return None, "path_not_directory"
    try:
        resolved = raw.resolve(strict=True)
    except OSError:
        return None, "path_unresolved"
    return resolved, None


def _priority(relative_path: str) -> tuple:
    name = relative_path.rsplit("/", 1)[-1].lower()
    for index, candidate in enumerate(PRIORITY_FILENAMES):
        if name == candidate:
            return (0, index, relative_path.lower())
    return (1, len(PRIORITY_FILENAMES), relative_path.lower())


def _decode(data: bytes) -> Tuple[Optional[str], str]:
    if b"\x00" in data[:4096]:
        return None, ""
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, ""


def discover_markdown_files(root: Path) -> Discovery:
    discovery = Discovery()
    candidates: List[Path] = []
    total_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        kept = []
        for name in sorted(dirnames):
            if name.startswith(".") or name.lower() in EXCLUDED_DIRS:
                discovery.skipped_directories += 1
                continue
            if os.path.islink(os.path.join(dirpath, name)):
                discovery.skipped_directories += 1
                continue
            kept.append(name)
        dirnames[:] = kept

        for name in sorted(filenames):
            suffix = Path(name).suffix.lower()
            if suffix not in MARKDOWN_SUFFIXES:
                continue
            absolute = Path(dirpath) / name
            try:
                if absolute.is_symlink():
                    target = absolute.resolve(strict=True)
                    if root not in target.parents and target != root:
                        discovery.skipped_files += 1
                        continue
                stat = absolute.stat()
            except OSError:
                discovery.unreadable.append(str(absolute))
                continue
            if not absolute.is_file():
                continue
            if stat.st_size > MAX_FILE_BYTES:
                discovery.skipped_large += 1
                continue
            if total_bytes + stat.st_size > MAX_TOTAL_BYTES:
                discovery.truncated = True
                break
            total_bytes += stat.st_size
            candidates.append(absolute)
        if discovery.truncated:
            break

    for absolute in sorted(candidates, key=lambda path: _priority(str(path.relative_to(root)).replace(os.sep, "/"))):
        if len(discovery.files) >= MAX_FILES:
            discovery.truncated = True
            break
        relative = str(absolute.relative_to(root)).replace(os.sep, "/")
        try:
            data = absolute.read_bytes()
        except OSError:
            discovery.unreadable.append(relative)
            continue
        text, encoding = _decode(data)
        if text is None:
            discovery.skipped_files += 1
            continue
        discovery.encodings[encoding] = discovery.encodings.get(encoding, 0) + 1
        discovery.files.append(
            MarkdownFile(relative_path=relative, absolute_path=absolute, text=text, encoding=encoding)
        )

    return discovery
