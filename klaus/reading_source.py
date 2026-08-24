"""Shared contract and identifiers for Klaus reading sources."""

from __future__ import annotations

from typing import Protocol

import numpy as np

NO_READING_SOURCE_INDEX = -1
DESK_VIEW_SOURCE_INDEX = -2
ACTIVE_READING_WINDOW_SOURCE_INDEX = -3
REMARKABLE_PAPER_PURE_SOURCE_INDEX = -4


class ReadingSource(Protocol):
    """Provide current visual and optional text context to Klaus."""

    def start(self) -> None: ...

    def capture_frame(self) -> np.ndarray | None: ...

    def capture_selected_text(self) -> str | None: ...

    @property
    def waiting_message(self) -> str: ...

