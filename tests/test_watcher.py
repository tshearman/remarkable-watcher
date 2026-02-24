"""Tests for watcher.py.

Fixture .rm files belong in tests/fixtures/.  Tests that require them are
automatically skipped when the files are absent so the suite is always
runnable without them.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from converter import (
    _HEADER_PREFIX,
    convert,
    get_rm_version,
    is_notebook,
)
from watcher import _RMHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


def _rm(path: Path, version: int) -> Path:
    """Write a minimal synthetic .rm file with the given version header."""
    header = _HEADER_PREFIX + str(version).encode() + b"          \n"
    path.write_bytes(header + b"\x00" * 16)
    return path


def _has(name: str) -> bool:
    return (FIXTURES / name).exists()


def _fixture(name: str) -> Path:
    return FIXTURES / name


# ---------------------------------------------------------------------------
# get_rm_version
# ---------------------------------------------------------------------------

class TestGetRmVersion:
    def test_version_6(self, tmp_path):
        assert get_rm_version(_rm(tmp_path / "p.rm", 6)) == 6

    def test_version_5(self, tmp_path):
        assert get_rm_version(_rm(tmp_path / "p.rm", 5)) == 5

    def test_version_3(self, tmp_path):
        assert get_rm_version(_rm(tmp_path / "p.rm", 3)) == 3

    def test_unrecognized_header_returns_none(self, tmp_path):
        f = tmp_path / "p.rm"
        f.write_bytes(b"not a remarkable file\n")
        assert get_rm_version(f) is None

    def test_empty_file_returns_none(self, tmp_path):
        f = tmp_path / "p.rm"
        f.write_bytes(b"")
        assert get_rm_version(f) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert get_rm_version(tmp_path / "ghost.rm") is None

    def test_malformed_version_returns_none(self, tmp_path):
        f = tmp_path / "p.rm"
        f.write_bytes(b"reMarkable .lines file, version=abc   \n")
        assert get_rm_version(f) is None

    # Real-file tests — skipped until fixture files are present.

    @pytest.mark.skipif(not _has("v6_page.rm"), reason="fixture v6_page.rm not present")
    def test_real_v6_file(self):
        assert get_rm_version(_fixture("v6_page.rm")) == 6

    @pytest.mark.skipif(not _has("v5_page.rm"), reason="fixture v5_page.rm not present")
    def test_real_v5_file(self):
        assert get_rm_version(_fixture("v5_page.rm")) == 5

    @pytest.mark.skipif(not _has("v3_page.rm"), reason="fixture v3_page.rm not present")
    def test_real_v3_file(self):
        assert get_rm_version(_fixture("v3_page.rm")) == 3


# ---------------------------------------------------------------------------
# is_notebook
# ---------------------------------------------------------------------------

class TestIsNotebook:
    """is_notebook() reads <root>/<uuid>.content next to the page directory."""

    def _write_content(self, root: Path, uuid: str, file_type: str) -> None:
        (root / f"{uuid}.content").write_text(json.dumps({"fileType": file_type}))

    def _make_rm(self, root: Path, uuid: str) -> Path:
        page_dir = root / uuid
        page_dir.mkdir(parents=True, exist_ok=True)
        rm = page_dir / "page.rm"
        rm.write_bytes(b"")
        return rm

    def test_empty_file_type_is_notebook(self, tmp_path):
        rm = self._make_rm(tmp_path, "abc123")
        self._write_content(tmp_path, "abc123", "")
        assert is_notebook(rm) is True

    def test_pdf_file_type_is_not_notebook(self, tmp_path):
        rm = self._make_rm(tmp_path, "abc123")
        self._write_content(tmp_path, "abc123", "pdf")
        assert is_notebook(rm) is False

    def test_epub_file_type_is_not_notebook(self, tmp_path):
        rm = self._make_rm(tmp_path, "abc123")
        self._write_content(tmp_path, "abc123", "epub")
        assert is_notebook(rm) is False

    def test_missing_content_file_assumed_notebook(self, tmp_path):
        rm = self._make_rm(tmp_path, "abc123")
        # no .content file written
        assert is_notebook(rm) is True

    def test_missing_file_type_field_assumed_notebook(self, tmp_path):
        rm = self._make_rm(tmp_path, "abc123")
        (tmp_path / "abc123.content").write_text(json.dumps({"pages": []}))
        assert is_notebook(rm) is True

    def test_malformed_content_file_assumed_notebook(self, tmp_path):
        rm = self._make_rm(tmp_path, "abc123")
        (tmp_path / "abc123.content").write_text("not valid json{{")
        assert is_notebook(rm) is True


# ---------------------------------------------------------------------------
# convert
# ---------------------------------------------------------------------------

class TestConvert:
    @patch("converter.subprocess.run")
    def test_v6_calls_rmc(self, mock_run, tmp_path):
        rm = _rm(tmp_path / "page.rm", 6)
        out = tmp_path / "out"
        out.mkdir()

        convert(rm, out)

        mock_run.assert_called_once_with(
            ["rmc", str(rm), "-o", str(out / "page.pdf")],
            check=True,
            capture_output=True,
        )

    @patch("converter.subprocess.run")
    def test_v5_calls_rm2pdf_on_file(self, mock_run, tmp_path):
        rm = _rm(tmp_path / "page.rm", 5)
        out = tmp_path / "out"
        out.mkdir()

        convert(rm, out)

        mock_run.assert_called_once_with(
            ["rm2pdf", str(rm), str(out / "page.pdf")],
            check=True,
            capture_output=True,
        )

    @patch("converter.subprocess.run")
    def test_pdf_annotation_skips_subprocess(self, mock_run, tmp_path):
        uuid = "abc123"
        page_dir = tmp_path / uuid
        page_dir.mkdir()
        rm = _rm(page_dir / "page.rm", 6)
        (tmp_path / f"{uuid}.content").write_text(json.dumps({"fileType": "pdf"}))
        out = tmp_path / "out"
        out.mkdir()

        convert(rm, out)

        mock_run.assert_not_called()

    @patch("converter.subprocess.run")
    def test_epub_annotation_skips_subprocess(self, mock_run, tmp_path):
        uuid = "abc123"
        page_dir = tmp_path / uuid
        page_dir.mkdir()
        rm = _rm(page_dir / "page.rm", 5)
        (tmp_path / f"{uuid}.content").write_text(json.dumps({"fileType": "epub"}))
        out = tmp_path / "out"
        out.mkdir()

        convert(rm, out)

        mock_run.assert_not_called()

    @patch("converter.subprocess.run")
    def test_unrecognized_file_skips_subprocess(self, mock_run, tmp_path):
        rm = tmp_path / "page.rm"
        rm.write_bytes(b"garbage")
        out = tmp_path / "out"
        out.mkdir()

        convert(rm, out)

        mock_run.assert_not_called()

    @patch("converter.subprocess.run")
    def test_v6_output_pdf_named_after_rm_stem(self, mock_run, tmp_path):
        rm = _rm(tmp_path / "my_note.rm", 6)
        out = tmp_path / "out"
        out.mkdir()

        convert(rm, out)

        _cmd = mock_run.call_args[0][0]
        assert _cmd[-1] == str(out / "my_note.pdf")

    @patch("converter._err")
    @patch("watcher.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_rmc_prints_error(self, _mock_run, mock_err, tmp_path):
        rm = _rm(tmp_path / "page.rm", 6)
        convert(rm, tmp_path)
        assert "rmc" in mock_err.print.call_args[0][0]

    @patch("converter._err")
    @patch("watcher.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_rm2pdf_prints_error(self, _mock_run, mock_err, tmp_path):
        rm = _rm(tmp_path / "page.rm", 5)
        convert(rm, tmp_path)
        assert "rm2pdf" in mock_err.print.call_args[0][0]

    @patch("converter._err")
    @patch("converter.subprocess.run")
    def test_subprocess_error_prints_stderr_message(self, mock_run, mock_err, tmp_path):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "rmc", stderr=b"rmc: unsupported feature"
        )
        rm = _rm(tmp_path / "page.rm", 6)

        convert(rm, tmp_path)

        assert "unsupported feature" in mock_err.print.call_args[0][0]

    @patch("converter._err")
    def test_unrecognized_file_prints_skip_message(self, mock_err, tmp_path):
        rm = tmp_path / "page.rm"
        rm.write_bytes(b"garbage")
        convert(rm, tmp_path)
        assert "skip" in mock_err.print.call_args[0][0]


# ---------------------------------------------------------------------------
# _RMHandler — event routing
# ---------------------------------------------------------------------------

class TestRMHandlerRouting:
    """Verify that filesystem events are dispatched or ignored correctly."""

    def _event(self, src: str, dest: str = None, is_dir: bool = False):
        e = MagicMock()
        e.is_directory = is_dir
        e.src_path = src
        e.dest_path = dest or src
        return e

    @patch("watcher.convert")
    def test_on_created_rm_file(self, mock_convert, tmp_path):
        h = _RMHandler(tmp_path, delay=0.0)
        h.on_created(self._event("/w/page.rm"))
        mock_convert.assert_called_once_with(Path("/w/page.rm"), tmp_path)

    @patch("watcher.convert")
    def test_on_modified_rm_file(self, mock_convert, tmp_path):
        h = _RMHandler(tmp_path, delay=0.0)
        h.on_modified(self._event("/w/page.rm"))
        mock_convert.assert_called_once_with(Path("/w/page.rm"), tmp_path)

    @patch("watcher.convert")
    def test_on_moved_uses_dest_path(self, mock_convert, tmp_path):
        h = _RMHandler(tmp_path, delay=0.0)
        h.on_moved(self._event(src="/w/old.txt", dest="/w/page.rm"))
        mock_convert.assert_called_once_with(Path("/w/page.rm"), tmp_path)

    @patch("watcher.convert")
    def test_non_rm_extension_ignored(self, mock_convert, tmp_path):
        h = _RMHandler(tmp_path, delay=0.0)
        h.on_created(self._event("/w/note.pdf"))
        h.on_modified(self._event("/w/note.txt"))
        h.on_moved(self._event(src="/w/a.rm", dest="/w/b.txt"))
        mock_convert.assert_not_called()

    @patch("watcher.convert")
    def test_directory_event_ignored(self, mock_convert, tmp_path):
        h = _RMHandler(tmp_path, delay=0.0)
        h.on_created(self._event("/w/subdir.rm", is_dir=True))
        mock_convert.assert_not_called()


# ---------------------------------------------------------------------------
# _RMHandler — debounce / scheduling
# ---------------------------------------------------------------------------

class TestRMHandlerDebounce:
    """Verify debounce timer mechanics without relying on real wall-clock time."""

    @patch("watcher.convert")
    def test_zero_delay_calls_convert_directly(self, mock_convert, tmp_path):
        h = _RMHandler(tmp_path, delay=0.0)
        h._schedule("/w/page.rm")
        mock_convert.assert_called_once_with(Path("/w/page.rm"), tmp_path)

    @patch("watcher.Timer")
    def test_nonzero_delay_creates_timer(self, MockTimer, tmp_path):
        mock_t = MagicMock()
        MockTimer.return_value = mock_t

        h = _RMHandler(tmp_path, delay=0.5)
        h._schedule("/w/page.rm")

        MockTimer.assert_called_once_with(0.5, convert, [Path("/w/page.rm"), tmp_path])
        mock_t.start.assert_called_once()

    @patch("watcher.Timer")
    def test_second_event_cancels_first_timer(self, MockTimer, tmp_path):
        first_t, second_t = MagicMock(), MagicMock()
        MockTimer.side_effect = [first_t, second_t]

        h = _RMHandler(tmp_path, delay=0.5)
        h._schedule("/w/page.rm")
        h._schedule("/w/page.rm")

        first_t.cancel.assert_called_once()
        second_t.start.assert_called_once()

    @patch("watcher.Timer")
    def test_different_files_get_independent_timers(self, MockTimer, tmp_path):
        t_a, t_b = MagicMock(), MagicMock()
        MockTimer.side_effect = [t_a, t_b]

        h = _RMHandler(tmp_path, delay=0.5)
        h._schedule("/w/a.rm")
        h._schedule("/w/b.rm")

        # Neither timer is cancelled
        t_a.cancel.assert_not_called()
        t_b.cancel.assert_not_called()
        assert MockTimer.call_count == 2

    @patch("watcher.Timer")
    def test_repeated_events_replace_pending_entry(self, MockTimer, tmp_path):
        timers = [MagicMock() for _ in range(3)]
        MockTimer.side_effect = timers

        h = _RMHandler(tmp_path, delay=0.5)
        for _ in range(3):
            h._schedule("/w/page.rm")

        # First two timers should be cancelled; third should be started
        timers[0].cancel.assert_called_once()
        timers[1].cancel.assert_called_once()
        timers[2].start.assert_called_once()
        # Only one pending entry for this path at any time
        assert len(h._pending) == 1


# ---------------------------------------------------------------------------
# Integration: real .rm files → correct converter invoked
# ---------------------------------------------------------------------------
# Drop files into tests/fixtures/ and these tests will automatically run.

class TestRealFileConversion:
    @pytest.mark.skipif(not _has("v6_page.rm"), reason="fixture v6_page.rm not present")
    @patch("converter.subprocess.run")
    def test_real_v6_file_uses_rmc(self, mock_run, tmp_path):
        convert(_fixture("v6_page.rm"), tmp_path)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "rmc"

    @pytest.mark.skipif(not _has("v5_page.rm"), reason="fixture v5_page.rm not present")
    @patch("converter.subprocess.run")
    def test_real_v5_file_uses_rm2pdf(self, mock_run, tmp_path):
        convert(_fixture("v5_page.rm"), tmp_path)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "rm2pdf"

    @pytest.mark.skipif(not _has("v3_page.rm"), reason="fixture v3_page.rm not present")
    @patch("converter.subprocess.run")
    def test_real_v3_file_uses_rm2pdf(self, mock_run, tmp_path):
        convert(_fixture("v3_page.rm"), tmp_path)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "rm2pdf"


# ---------------------------------------------------------------------------
# V6 multi-page notebook fixture
# ---------------------------------------------------------------------------
# Populate tests/fixtures/v6_notebook/ with a real notebook from your reMarkable
# sync directory.  Copy the UUID directory and its sibling files:
#
#   tests/fixtures/v6_notebook/
#     <uuid>.content        ← fileType should be "" (notebook)
#     <uuid>.metadata
#     <uuid>/
#       <page1-uuid>.rm
#       <page2-uuid>.rm
#       ...
#
# All tests in this class are skipped until at least two .rm files are present.

_V6_NOTEBOOK = FIXTURES / "v6_notebook"


def _find_v6_rm_files() -> list:
    if not _V6_NOTEBOOK.is_dir():
        return []
    content_files = list(_V6_NOTEBOOK.glob("*.content"))
    if not content_files:
        return []
    page_dir = _V6_NOTEBOOK / content_files[0].stem
    if not page_dir.is_dir():
        return []
    return sorted(page_dir.glob("*.rm"))


_V6_RM_FILES = _find_v6_rm_files()

_V6_SKIP = pytest.mark.skipif(
    len(_V6_RM_FILES) < 2,
    reason="v6_notebook fixture not present (need ≥2 pages in tests/fixtures/v6_notebook/)",
)


@_V6_SKIP
class TestV6NotebookFixture:
    """Integration tests against a real multi-page v6 notebook."""

    def test_fixture_has_multiple_pages(self):
        assert len(_V6_RM_FILES) >= 2

    def test_content_file_marks_as_notebook(self):
        content_file = next(_V6_NOTEBOOK.glob("*.content"))
        data = json.loads(content_file.read_text())
        assert data.get("fileType", "") not in ("pdf", "epub")

    def test_all_pages_are_version_6(self):
        for rm in _V6_RM_FILES:
            assert get_rm_version(rm) == 6, f"{rm.name} is not version 6"

    def test_all_pages_identified_as_notebook(self):
        for rm in _V6_RM_FILES:
            assert is_notebook(rm) is True, f"{rm.name} was not identified as notebook"

    @patch("converter.subprocess.run")
    def test_each_page_dispatches_to_rmc(self, mock_run, tmp_path):
        for rm in _V6_RM_FILES:
            convert(rm, tmp_path)

        assert mock_run.call_count == len(_V6_RM_FILES)
        for call_args, rm in zip(mock_run.call_args_list, _V6_RM_FILES):
            cmd = call_args[0][0]
            assert cmd[0] == "rmc"
            assert cmd[1] == str(rm)

    @patch("converter.subprocess.run")
    def test_each_page_output_named_after_stem(self, mock_run, tmp_path):
        for rm in _V6_RM_FILES:
            convert(rm, tmp_path)

        for call_args, rm in zip(mock_run.call_args_list, _V6_RM_FILES):
            cmd = call_args[0][0]
            assert cmd[-1] == str(tmp_path / f"{rm.stem}.pdf")
