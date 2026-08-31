"""Create a clean, deterministic source ZIP for cross-platform distribution."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {
    ".git",
    ".next",
    ".pnpm-store",
    ".pytest_cache",
    ".runtime",
    ".venv",
    "__MACOSX",
    "__pycache__",
    "node_modules",
}
EXCLUDED_NAMES = {".DS_Store", ".env", ".env.local"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
ABSOLUTE_DEVELOPER_PATH = re.compile(rb"^#!.*(?:/Users/|/home/[^/]+/)")


def included_files(*, strict: bool = False) -> list[Path]:
    files: list[Path] = []
    violations: list[str] = []
    for directory, names, filenames in os.walk(ROOT):
        excluded_directories = sorted(
            name for name in names if name in EXCLUDED_DIRECTORIES
        )
        if strict:
            violations.extend(
                f"excluded directory present: {(Path(directory) / name).relative_to(ROOT)}"
                for name in excluded_directories
            )
        names[:] = sorted(name for name in names if name not in EXCLUDED_DIRECTORIES)
        base = Path(directory)
        for filename in sorted(filenames):
            path = base / filename
            relative = path.relative_to(ROOT)
            if filename in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
                if strict:
                    violations.append(f"excluded file present: {relative}")
                continue
            if path.is_symlink():
                violations.append(f"symbolic link: {relative}")
                continue
            with path.open("rb") as source:
                first_line = source.readline(4096)
            if ABSOLUTE_DEVELOPER_PATH.search(first_line):
                violations.append(f"absolute developer shebang: {relative}")
            files.append(path)
    if violations:
        raise RuntimeError("\n".join(violations))
    return files


def write_archive(output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = Path("belgedogrula") / path.relative_to(ROOT)
            info = ZipInfo(relative.as_posix(), date_time=(2026, 8, 13, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    files = included_files(strict=args.check)
    if args.check:
        print(f"Clean source check passed: {len(files)} files")
        return 0
    output = args.output or ROOT.parent / "belgedogrula-release.zip"
    write_archive(output.resolve(), files)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Release hygiene check failed:\n{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
