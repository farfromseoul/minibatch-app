"""파일 해시. 멱등 판정(규칙 3)과 산출물 기록(규칙 6)에 쓴다."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def sha256_path(path: Path) -> str:
    """파일이면 내용의 해시, 폴더면 (상대 경로, 내용) 목록의 해시."""
    h = hashlib.sha256()
    if path.is_dir():
        for f in sorted(p for p in path.rglob("*") if p.is_file()):
            h.update(str(f.relative_to(path)).encode())
            h.update(b"\0")
            h.update(_file_digest(f).encode())
    else:
        h.update(_file_digest(path).encode())
    return h.hexdigest()


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inputs_hash(job_dir: Path, inputs: Iterable[str]) -> str:
    h = hashlib.sha256()
    for rel in inputs:
        p = job_dir / rel
        h.update(rel.encode())
        h.update(b"=")
        h.update((sha256_path(p) if p.exists() else "missing").encode())
        h.update(b";")
    return h.hexdigest()
