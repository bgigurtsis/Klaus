"""Session list panel for the left sidebar."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QInputDialog,
    QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from klaus.ui import theme
from klaus.ui.shared.relative_time import format_relative_time


def _dark_input_dialog(
    parent: QWidget, title: str, label: str, text: str = "",
) -> tuple[str, bool]:
    """QInputDialog.getText replacement with dark title bar and minimum width."""
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setTextValue(text)
    dlg.setMinimumWidth(350)
    theme.apply_dark_titlebar(dlg)
    ok = dlg.exec()
    return dlg.textValue(), bool(ok)


def _dark_question_box(
    parent: QWidget, title: str, text: str,
) -> bool:
    """QMessageBox.question replacement with dark title bar."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setMinimumWidth(350)
    theme.apply_dark_titlebar(box)
    return box.exec() == QMessageBox.StandardButton.Yes


class SessionPanel(QWidget):
    """Sidebar widget listing sessions with create / rename / delete."""

    session_selected = pyqtSignal(str)         # session_id
    new_session_requested = pyqtSignal(str)    # title
    rename_requested = pyqtSignal(str, str)    # session_id, new_title
    delete_requested = pyqtSignal(str)         # session_id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._sessions: list[dict] = []
        self._current_id: str | None = None
        self._init_ui()

    @property
    def current_id(self) -> str | None:
        return self._current_id

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)

        title = QLabel("SESSIONS")
        title.setObjectName("session-panel-title")
        header.addWidget(title)
        header.addStretch()

        new_btn = QPushButton("+ New")
        new_btn.setObjectName("session-new-btn")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setFixedHeight(24)
        new_btn.clicked.connect(self._on_new_session)
        header.addWidget(new_btn)

        layout.addLayout(header)

        self._list = QListWidget()
        self._list.setObjectName("session-list")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, stretch=1)

    # -- Public API --

    def set_sessions(
        self, sessions: list[dict], current_id: str | None = None,
    ) -> None:
        """Populate the list.  Each dict: id, title, updated_at, exchange_count."""
        self._sessions = sessions
        self._current_id = current_id

        self._list.blockSignals(True)
        self._list.clear()

        for s in sessions:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            item.setSizeHint(QSize(0, 48))

            meta_parts = []
            if "exchange_count" in s:
                meta_parts.append(f"{s['exchange_count']} Q&A")
            if "updated_at" in s:
                meta_parts.append(format_relative_time(s["updated_at"]))
            meta = " \u00b7 ".join(meta_parts)

            label = QLabel()
            label.setObjectName("session-item-label")
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setText(
                f'<div style="color:{theme.TEXT_PRIMARY};'
                f'font-size:{theme.FONT_SIZE_SMALL}px;font-weight:600;">'
                f'{s["title"]}</div>'
                f'<div style="color:{theme.TEXT_MUTED};'
                f'font-size:{theme.FONT_SIZE_CAPTION}px;margin-top:2px;">'
                f'{meta}</div>'
            )
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

            self._list.addItem(item)
            self._list.setItemWidget(item, label)

            if current_id and s["id"] == current_id:
                self._list.setCurrentItem(item)

        self._list.blockSignals(False)

    def select_session(self, session_id: str) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == session_id:
                self._list.blockSignals(True)
                self._list.setCurrentItem(item)
                self._list.blockSignals(False)
                self._current_id = session_id
                return

    # -- Slots --

    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._sessions):
            sid = self._sessions[row]["id"]
            if sid != self._current_id:
                self._current_id = sid
                self.session_selected.emit(sid)

    def _on_new_session(self) -> None:
        title, ok = _dark_input_dialog(
            self, "New Session", "Paper or book title:",
        )
        if ok and title.strip():
            self.new_session_requested.emit(title.strip())

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return

        row = self._list.row(item)
        if row < 0 or row >= len(self._sessions):
            return
        session = self._sessions[row]

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        delete_action.setData("delete")

        action = menu.exec(self._list.mapToGlobal(pos))
        if action is None:
            return

        if action == rename_action:
            new_title, ok = _dark_input_dialog(
                self, "Rename Session", "New title:", text=session["title"],
            )
            if ok and new_title.strip():
                self.rename_requested.emit(session["id"], new_title.strip())

        elif action == delete_action:
            confirmed = _dark_question_box(
                self,
                "Delete Session",
                f"Delete \"{session['title']}\" and all its exchanges?",
            )
            if confirmed:
                self.delete_requested.emit(session["id"])
