#!/usr/bin/env python3
"""remarkable_watcher — watch directories for .rm notebook pages and convert to PDF."""

import time
from pathlib import Path
from threading import Lock, Timer

import click
from rich.panel import Panel
from rich.table import Table
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from typing import Optional

from converter import _out, convert, needs_conversion, load_metadata


class _RMHandler(FileSystemEventHandler):
    def __init__(
        self,
        output_dir: Path,
        delay: float,
        metadata: dict,
        meta_lock: Lock,
        staging_dir: Optional[Path],
    ) -> None:
        self.output_dir = output_dir
        self.delay = delay
        self.metadata = metadata
        self.meta_lock = meta_lock
        self.staging_dir = staging_dir
        self._pending: dict = {}

    def _schedule(self, path: str) -> None:
        kwargs = {"metadata": self.metadata, "meta_lock": self.meta_lock, "staging_dir": self.staging_dir}
        if self.delay > 0:
            if path in self._pending:
                self._pending[path].cancel()
            t = Timer(self.delay, convert, [Path(path), self.output_dir], kwargs)
            self._pending[path] = t
            t.start()
        else:
            convert(Path(path), self.output_dir, **kwargs)

    def on_created(self, event) -> None:
        if not event.is_directory and event.src_path.endswith(".rm"):
            self._schedule(event.src_path)

    def on_modified(self, event) -> None:
        if not event.is_directory and event.src_path.endswith(".rm"):
            self._schedule(event.src_path)

    def on_moved(self, event) -> None:
        if not event.is_directory and event.dest_path.endswith(".rm"):
            self._schedule(event.dest_path)


@click.command()
@click.argument(
    "watch_dirs",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    metavar="DIR",
)
@click.option(
    "-o", "--output",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="DIR",
    help="Directory where PDFs will be written.",
)
@click.option(
    "-d", "--delay",
    default=0.0,
    type=float,
    metavar="SECS",
    show_default=True,
    help="Debounce delay in seconds before converting.",
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    show_default=True,
    help="Watch directories recursively.",
)
@click.option(
    "--verify",
    is_flag=True,
    default=False,
    help="Also reprocess files whose output PDF is missing or has changed.",
)
@click.option(
    "--staging",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="DIR",
    help="Directory for temporary files during conversion (default: system temp).",
)
def main(
    watch_dirs: tuple,
    output: Path,
    delay: float,
    recursive: bool,
    verify: bool,
    staging: Optional[Path],
) -> None:
    """Watch directories for .rm files and convert each page to PDF.

    Uses rmc for version 6+ files and rm2pdf for older versions.
    """
    output.mkdir(parents=True, exist_ok=True)

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="cyan")
    grid.add_column()
    for d in watch_dirs:
        suffix = "  [dim]recursive[/dim]" if recursive else ""
        grid.add_row("watching", f"{d}{suffix}")
    grid.add_row("output", str(output))
    if delay:
        grid.add_row("delay", f"{delay}s")
    _out.print(Panel(grid, title="[bold]remarkable_watcher[/bold]", border_style="cyan dim"))

    metadata = load_metadata(output)
    meta_lock = Lock()

    # Scan for new or changed files and convert them before starting the watcher.
    pattern = "**/*.rm" if recursive else "*.rm"
    rm_files = [f for d in watch_dirs for f in sorted(d.glob(pattern))]
    pending = [f for f in rm_files if needs_conversion(f, output, metadata, verify=verify)]

    total = len(rm_files)
    if pending:
        _out.print(
            f"[dim]found {len(pending)} new/changed"
            f" of {total} .rm file{'s' if total != 1 else ''} — converting…[/dim]"
        )
        for f in pending:
            convert(f, output, metadata=metadata, meta_lock=meta_lock, staging_dir=staging)
    else:
        _out.print(
            f"[dim]{total} .rm file{'s' if total != 1 else ''} up to date[/dim]"
        )

    handler = _RMHandler(output, delay=delay, metadata=metadata, meta_lock=meta_lock, staging_dir=staging)
    observer = Observer()
    for d in watch_dirs:
        observer.schedule(handler, str(d), recursive=recursive)

    _out.print("[dim]watching for changes · Ctrl+C to stop[/dim]")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _out.print("\n[dim]stopping…[/dim]")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
