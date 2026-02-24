#!/usr/bin/env python3
"""rm converter — convert individual .rm notebook pages to PDF.

Uses rmc for version 6+ files, rm2pdf for older versions.
Can be used as a library (import convert) or as a standalone CLI tool.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

# Header prefix common to all known .rm formats
_HEADER_PREFIX = b"reMarkable .lines file, version="

_METADATA_FILE = ".rm_metadata.json"

# PDFs produced by rmc+Inkscape for a blank page are ~2-3 KB.
# Any page with at least one mark produces 20 KB+.
_BLANK_PDF_THRESHOLD = 10_000  # bytes

_out = Console()
_err = Console(stderr=True)


def file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_metadata(output_dir: Path) -> dict:
    """Load the conversion index from output_dir/.rm_metadata.json."""
    meta_file = output_dir / _METADATA_FILE
    if not meta_file.exists():
        return {}
    try:
        data = json.loads(meta_file.read_text())
        if any(not isinstance(v, dict) for v in data.values()):
            _err.print(
                f"[yellow]warning:[/yellow] {meta_file} uses an incompatible format "
                "and will be rebuilt — all files will be reprocessed"
            )
            meta_file.unlink()
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_metadata(output_dir: Path, metadata: dict) -> None:
    """Atomically write the conversion index to output_dir/.rm_metadata.json."""
    meta_file = output_dir / _METADATA_FILE
    tmp = meta_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(metadata, indent=2))
    tmp.replace(meta_file)


def needs_conversion(
    rm_file: Path,
    output_dir: Path,
    metadata: dict,
    verify: bool = False,
) -> bool:
    """Return True if rm_file should be (re)converted.

    Always checks whether the input file has changed since last conversion.
    With verify=True, also checks whether the output PDF is present and unmodified.
    """
    entry = metadata.get(str(rm_file))
    if entry is None:
        return True
    if file_hash(rm_file) != entry["input"]:
        return True
    if verify:
        output_pdf = output_dir / f"{rm_file.stem}.pdf"
        if not output_pdf.exists():
            return True
        if file_hash(output_pdf) != entry["output"]:
            return True
    return False


def get_rm_version(filepath: Path) -> Optional[int]:
    """Read the .rm file version from its header. Returns None if unrecognized."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(64)
        if header.startswith(_HEADER_PREFIX):
            rest = header[len(_HEADER_PREFIX):].decode("ascii", errors="ignore")
            return int(rest.split()[0])
    except (OSError, ValueError):
        pass
    return None


def is_notebook(rm_file: Path) -> bool:
    """Return True if the .rm file is a notebook page rather than a PDF/ePub annotation.

    Reads the sibling <uuid>.content file (standard reMarkable sync layout):
        <root>/<uuid>.content
        <root>/<uuid>/<page>.rm   ← rm_file

    Returns True (process) when the content file is absent or unreadable, so
    standalone .rm files outside the normal bundle structure are not silently
    dropped.
    """
    content_file = rm_file.parent.parent / (rm_file.parent.name + ".content")
    if not content_file.exists():
        return True
    try:
        data = json.loads(content_file.read_text())
        return data.get("fileType", "") not in ("pdf", "epub")
    except (json.JSONDecodeError, OSError):
        return True


def convert(
    rm_file: Path,
    output_dir: Path,
    metadata: Optional[dict] = None,
    meta_lock: Optional[threading.Lock] = None,
    staging_dir: Optional[Path] = None,
) -> None:
    """Convert a .rm file to PDF, dispatching to rmc (v6+) or rm2pdf (pre-v6).

    Always operates on individual .rm files — one PDF per page.
    Silently skips pages that belong to PDF or ePub annotations.
    If metadata and meta_lock are provided, updates the conversion index on success.
    """
    if not is_notebook(rm_file):
        return

    version = get_rm_version(rm_file)
    if version is None:
        _err.print(f"[yellow]skip[/yellow]  {rm_file.name}: unrecognized header")
        return

    output_pdf = output_dir / f"{rm_file.stem}.pdf"
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=staging_dir)
    os.close(fd)
    os.unlink(tmp_path)  # remove placeholder — rmc/rm2pdf must create the file itself
    tmp_pdf = Path(tmp_path)
    if version >= 6:
        cmd = ["rmc", str(rm_file), "-o", str(tmp_pdf)]
    else:
        cmd = ["rm2pdf", str(rm_file), str(tmp_pdf)]

    _out.print(
        f"[dim]→[/dim] [bold][v{version}][/bold]"
        f" {rm_file.name} [dim]converting…[/dim]"
    )
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if tmp_pdf.stat().st_size <= _BLANK_PDF_THRESHOLD:
            tmp_pdf.unlink()
            _out.print(f"[dim]·[/dim] [bold][v{version}][/bold] {rm_file.name} [dim]blank — skipped[/dim]")
            return
        shutil.move(str(tmp_pdf), output_pdf)
        _out.print(
            f"[green]✓[/green] [bold][v{version}][/bold]"
            f" {rm_file.name} [dim]→[/dim] {output_pdf.name}"
        )
        if metadata is not None:
            entry = {"input": file_hash(rm_file), "output": file_hash(output_pdf)}
            with (meta_lock or threading.Lock()):
                metadata[str(rm_file)] = entry
                save_metadata(output_dir, metadata)
    except subprocess.CalledProcessError as e:
        tmp_pdf.unlink(missing_ok=True)  # may not exist if the tool never wrote it
        stderr = e.stderr.decode(errors="replace").strip()
        reason = stderr.splitlines()[-1] if stderr else str(e)
        _err.print(f"[red]✗[/red] {rm_file.name}: {reason}")
    except FileNotFoundError:
        tmp_pdf.unlink(missing_ok=True)  # may not exist if the tool never wrote it
        tool = "rmc" if version >= 6 else "rm2pdf"
        _err.print(f"[red]error:[/red] '{tool}' not found — install it and try again")


@click.command()
@click.argument(
    "paths",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
    metavar="PATH",
)
@click.option(
    "-o", "--output",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="DIR",
    help="Directory where PDFs will be written.",
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    show_default=True,
    help="Scan directories recursively (applies to directory paths only).",
)
@click.option(
    "--staging",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="DIR",
    help="Directory for temporary files during conversion (default: system temp).",
)
def main(paths: tuple, output: Path, recursive: bool, staging: Optional[Path]) -> None:
    """Convert .rm notebook pages to PDF.

    Each PATH may be a .rm file or a directory to scan for .rm files.
    PDF and ePub annotations are silently skipped.
    """
    output.mkdir(parents=True, exist_ok=True)

    rm_files: list[Path] = []
    for p in paths:
        if p.suffix == ".rm":
            rm_files.append(p)
        elif p.is_dir():
            pattern = "**/*.rm" if recursive else "*.rm"
            rm_files.extend(sorted(p.glob(pattern)))

    if not rm_files:
        _err.print("[yellow]warning:[/yellow] no .rm files found")
        return

    for rm in rm_files:
        convert(rm, output, staging_dir=staging)


if __name__ == "__main__":
    main()
