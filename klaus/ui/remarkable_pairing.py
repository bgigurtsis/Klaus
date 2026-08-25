"""Pairing controls for the reMarkable Paper Pure reading source."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import klaus.config as config
from klaus.remarkable_reading_source import RemarkableError, pair_tablet
from klaus.ui import theme


class RemarkablePairingDialog(QDialog):
    """Verify a tablet connection before persisting its certificate and credentials."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pair reMarkable Paper Pure")
        self.setMinimumWidth(520)
        self.setStyleSheet(theme.application_stylesheet())

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Use this fallback if the README setup script could not pair automatically. "
            "Enter the details shown by klaus-remarkable-pairing on the tablet. "
            "Klaus will test the service and pin this tablet's certificate."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.address_edit = QLineEdit(config.REMARKABLE_ADDRESS)
        self.address_edit.setPlaceholderText("https://10.11.99.1:2001")
        self.username_edit = QLineEdit(config.REMARKABLE_USERNAME)
        self.username_edit.setPlaceholderText("klaus")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Pairing password")
        form.addRow("Tablet address", self.address_edit)
        form.addRow("Username", self.username_edit)
        form.addRow("Pairing password", self.password_edit)
        layout.addLayout(form)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.pair_button = QPushButton("Test and pair")
        self.pair_button.setObjectName("wizard-primary-btn")
        self.pair_button.clicked.connect(self._pair)
        buttons.addWidget(cancel)
        buttons.addWidget(self.pair_button)
        layout.addLayout(buttons)

    def _pair(self) -> None:
        address = self.address_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not address or not username or not password:
            QMessageBox.warning(self, "Pairing details required", "Enter all three pairing values.")
            return
        self.pair_button.setEnabled(False)
        self.status_label.setText("Testing version, login, and screenshot...")
        try:
            result = pair_tablet(address, username, password)
            config.save_remarkable_connection(
                result.address,
                result.username,
                password,
                result.certificate_sha256,
            )
            config.reload()
        except (RemarkableError, ValueError, config.secrets_store.SecretsStoreError) as exc:
            self.status_label.setText(str(exc))
            self.pair_button.setEnabled(True)
            return
        self.status_label.setText(
            f"Paired {result.frame_width} x {result.frame_height} screen, service {result.version}."
        )
        QMessageBox.information(
            self,
            "Paper Pure paired",
            "Klaus decoded a fresh screenshot and pinned the tablet certificate.",
        )
        self.accept()


def open_remarkable_pairing(parent: QWidget | None = None) -> bool:
    """Open the pairing dialog and return whether pairing succeeded."""
    return RemarkablePairingDialog(parent).exec() == QDialog.DialogCode.Accepted
