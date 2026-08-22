import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from klaus.macos_reading_source import (
    ACTIVE_READING_WINDOW_MODE,
    DESK_VIEW_MODE,
    MacOSReadingSource,
    _select_window,
)


def _window(
    window_id: int,
    owner: str,
    *,
    pid: int,
    title: str = "",
    width: int = 1200,
    height: int = 800,
) -> dict:
    return {
        "kCGWindowNumber": window_id,
        "kCGWindowOwnerPID": pid,
        "kCGWindowOwnerName": owner,
        "kCGWindowName": title,
        "kCGWindowLayer": 0,
        "kCGWindowAlpha": 1,
        "kCGWindowIsOnscreen": True,
        "kCGWindowBounds": {"Width": width, "Height": height},
    }


class TestWindowSelection:
    def test_desk_view_mode_selects_desk_view(self):
        windows = [
            _window(1, "Preview", pid=10, title="paper.pdf"),
            _window(2, "Desk View", pid=11),
        ]

        target = _select_window(windows, DESK_VIEW_MODE, own_pid=99)

        assert target is not None
        assert target.window_id == 2

    def test_active_mode_uses_frontmost_non_desk_view_window(self):
        windows = [
            _window(1, "Desk View", pid=11),
            _window(2, "Preview", pid=12, title="paper.pdf"),
            _window(3, "Google Chrome", pid=13, title="notes"),
        ]

        target = _select_window(
            windows,
            ACTIVE_READING_WINDOW_MODE,
            own_pid=99,
        )

        assert target is not None
        assert target.window_id == 2

    def test_active_mode_excludes_klaus_process(self):
        windows = [
            _window(1, "Klaus", pid=99),
            _window(2, "Preview", pid=12, title="paper.pdf"),
        ]

        target = _select_window(
            windows,
            ACTIVE_READING_WINDOW_MODE,
            own_pid=99,
        )

        assert target is not None
        assert target.owner_name == "Preview"

    def test_active_mode_excludes_computer_use_controls(self):
        windows = [
            _window(1, "ChatGPT", pid=10, title="Computer Use Controls"),
            _window(2, "Preview", pid=12, title="paper.pdf"),
        ]

        target = _select_window(
            windows,
            ACTIVE_READING_WINDOW_MODE,
            own_pid=99,
        )

        assert target is not None
        assert target.window_id == 2


class TestMacOSReadingSource:
    def test_start_accepts_permission_granted_by_request(self):
        quartz = SimpleNamespace(
            CGPreflightScreenCaptureAccess=lambda: False,
            CGRequestScreenCaptureAccess=lambda: True,
        )
        source = MacOSReadingSource(DESK_VIEW_MODE)

        with patch.object(sys, "platform", "darwin"), patch.dict(
            sys.modules, {"Quartz": quartz}
        ):
            source.start()

    @patch("klaus.macos_reading_source._capture_window_image")
    @patch("klaus.macos_reading_source._copy_window_infos")
    def test_capture_tracks_target_and_returns_frame(self, mock_infos, mock_capture):
        frame = np.ones((100, 200, 3), dtype=np.uint8)
        mock_infos.return_value = [_window(7, "Desk View", pid=50)]
        mock_capture.return_value = frame
        source = MacOSReadingSource(DESK_VIEW_MODE)

        result = source.capture_frame()

        assert result is frame
        assert source.target is not None
        assert source.target.window_id == 7
        mock_capture.assert_called_once_with(7)

    @patch("klaus.macos_reading_source._capture_window_image")
    @patch("klaus.macos_reading_source._copy_window_infos")
    def test_capture_skips_black_protected_window(self, mock_infos, mock_capture):
        black = np.zeros((100, 200, 3), dtype=np.uint8)
        paper = np.full((100, 200, 3), 255, dtype=np.uint8)
        mock_infos.return_value = [
            _window(7, "Overlay", pid=50),
            _window(8, "Preview", pid=51, title="paper.pdf"),
        ]
        mock_capture.side_effect = [black, paper]
        source = MacOSReadingSource(ACTIVE_READING_WINDOW_MODE)

        result = source.capture_frame()

        assert result is paper
        assert source.target is not None
        assert source.target.window_id == 8

    @patch("klaus.macos_reading_source._selected_text_for_pid")
    @patch(
        "klaus.macos_reading_source._capture_window_image",
        return_value=np.ones((100, 200, 3), dtype=np.uint8),
    )
    @patch("klaus.macos_reading_source._copy_window_infos")
    def test_active_window_returns_selected_text(
        self, mock_infos, _mock_capture, mock_selected
    ):
        mock_infos.return_value = [_window(8, "Preview", pid=51, title="paper.pdf")]
        mock_selected.return_value = "selected passage"
        source = MacOSReadingSource(ACTIVE_READING_WINDOW_MODE)

        assert source.capture_selected_text() == "selected passage"
        mock_selected.assert_called_once_with(51)
