"""Create a clean PayPilot release ZIP without local secrets/runtime state."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git", ".github-cache", ".idea", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".venv", "venv", "__pycache__", "node_modules", "dist", "build", "htmlcov",
}
EXCLUDED_NAMES = {".env", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".zip"}
EXCLUDED_RUNTIME_SUFFIXES = (".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")


def allowed(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.endswith(EXCLUDED_RUNTIME_SUFFIXES):
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default=str(ROOT.parent / "paypilot-ai-faang-final.zip"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and allowed(p) and p.resolve() != output)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            arcname = Path("paypilot-ai") / path.relative_to(ROOT)
            zf.write(path, arcname.as_posix())
    print(f"Created {output} with {len(files)} files")


if __name__ == "__main__":
    main()
