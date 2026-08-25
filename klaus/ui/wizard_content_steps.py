"""Setup-wizard content steps: welcome, API keys, about-you, done.

Mixin for SetupWizard. Builders add pages to ``self._stack`` and store the
widgets they need as attributes on the wizard.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import klaus.config as config
from klaus.ui import theme
from klaus.ui.shared.key_validation import KEY_PATTERNS, KEY_URLS, validate_api_key
from klaus.ui.wizard_widgets import NUM_STEPS


class ContentStepsMixin:
    """Welcome, API-key, about-you, and done pages."""

    # -- Step 1: Welcome --

    def _build_step_welcome(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 22, 36, 20)
        layout.setSpacing(12)

        title = QLabel("Welcome to Klaus")
        title.setObjectName("wizard-welcome-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Klaus can keep you on the page while you ask, check, and save ideas. "
            "Use this short loop to get started."
        )
        subtitle.setObjectName("wizard-welcome-subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        card_specs = [
            (
                "Read Anything",
                "Choose Desk View for paper, or keep any app window frontmost. Klaus can "
                "use selected text before it falls back to a window image.",
            ),
            (
                "Ask by Voice",
                "Speak in hands-free mode, or hold the push-to-talk key. Start speaking "
                "over an answer to interrupt it and ask a follow-up.",
            ),
            (
                "Remember",
                "Each reading session can keep its questions, answers, and working context.",
            ),
            (
                "Save to Obsidian",
                "Choose your vault during setup. Then say which note to use, such as "
                '"Save this to Research/Agent Notes.md."',
            ),
        ]

        cards_grid = QGridLayout()
        cards_grid.setContentsMargins(0, 2, 0, 0)
        cards_grid.setHorizontalSpacing(12)
        cards_grid.setVerticalSpacing(12)
        for index, (card_title, card_body) in enumerate(card_specs):
            cards_grid.addWidget(
                self._build_welcome_card(card_title, card_body),
                index // 2,
                index % 2,
            )
        cards_grid.setColumnStretch(0, 1)
        cards_grid.setColumnStretch(1, 1)
        layout.addLayout(cards_grid)

        footer = QLabel(
            "Point to the passage, ask one question, then follow up. "
            "You can change every setup choice later in Settings."
        )
        footer.setObjectName("wizard-welcome-footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)
        layout.addWidget(footer)

        layout.addSpacing(6)

        btn = QPushButton("Get Started")
        btn.setObjectName("wizard-primary-btn")
        btn.setFixedWidth(200)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._set_step(1))
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

        self._stack.addWidget(page)

    def _build_welcome_card(self, title: str, body: str) -> QWidget:
        card = QWidget()
        card.setObjectName("wizard-welcome-card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("wizard-welcome-card-title")
        title_label.setWordWrap(True)
        card_layout.addWidget(title_label)

        body_label = QLabel(body)
        body_label.setObjectName("wizard-welcome-card-body")
        body_label.setWordWrap(True)
        card_layout.addWidget(body_label)

        card_layout.addStretch(1)
        return card

    # -- Step 2: API keys --

    def _build_step_api_keys(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(8)

        heading = QLabel("Choose your live conversation")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)
        description = QLabel(
            "GPT Live 2.1 mini is the default. Choose Gemini Live when you need "
            "Google Search grounding."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SMALL}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(description)
        layout.addSpacing(8)

        model_row = QHBoxLayout()
        model_label = QLabel("Conversation model")
        model_label.setFixedWidth(135)
        model_row.addWidget(model_label)
        self._live_model_combo = QComboBox()
        for model, details in config.LIVE_MODELS.items():
            self._live_model_combo.addItem(details["label"], model)
        selected_model = self._live_model_combo.findData(self._collected["live_model"])
        self._live_model_combo.setCurrentIndex(max(0, selected_model))
        self._live_model_combo.currentIndexChanged.connect(self._on_live_model_changed)
        model_row.addWidget(self._live_model_combo, stretch=1)
        layout.addLayout(model_row)

        effort_row = QHBoxLayout()
        effort_label = QLabel("Reasoning effort")
        effort_label.setFixedWidth(135)
        effort_row.addWidget(effort_label)
        self._reasoning_effort_combo = QComboBox()
        for effort in ("low", "medium", "high"):
            self._reasoning_effort_combo.addItem(effort.capitalize(), effort)
        selected_effort = self._reasoning_effort_combo.findData(
            self._collected["reasoning_effort"]
        )
        self._reasoning_effort_combo.setCurrentIndex(max(0, selected_effort))
        effort_row.addWidget(self._reasoning_effort_combo, stretch=1)
        layout.addLayout(effort_row)

        self._key_edits: dict[str, QLineEdit] = {}
        self._key_indicators: dict[str, QLabel] = {}
        self._key_hints: dict[str, QLabel] = {}
        self._key_valid: dict[str, bool] = {}
        self._key_names: dict[str, QLabel] = {}

        for label, slug, prefix, min_len in KEY_PATTERNS:
            row = QHBoxLayout()
            row.setSpacing(8)

            name = QLabel(label)
            name.setFixedWidth(135)
            name.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
                "background: transparent; border: none;"
            )
            row.addWidget(name)

            edit = QLineEdit()
            existing_key = bool(self._collected.get(slug))
            edit.setPlaceholderText("Already configured" if existing_key else f"{prefix}...")
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setMinimumWidth(300)
            edit.textChanged.connect(lambda _, s=slug: self._validate_key(s))
            self._key_edits[slug] = edit
            self._key_names[slug] = name
            row.addWidget(edit, stretch=1)

            indicator = QLabel("✓" if existing_key else "")
            indicator.setFixedWidth(24)
            indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setStyleSheet("background: transparent; border: none;")
            if existing_key:
                indicator.setStyleSheet(
                    f"color: {theme.KLAUS_ACCENT}; font-size: 18px; "
                    "background: transparent; border: none;"
                )
            self._key_indicators[slug] = indicator
            row.addWidget(indicator)

            link = QPushButton("Get a key")
            link.setObjectName("wizard-link-btn")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setFixedWidth(80)
            url = KEY_URLS[slug]
            link.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(link)

            layout.addLayout(row)

            hint = QLabel("")
            hint.setStyleSheet(
                f"color: {theme.ERROR_COLOR}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none; padding-left: 98px;"
            )
            hint.setVisible(False)
            self._key_hints[slug] = hint
            layout.addWidget(hint)
            self._key_valid[slug] = existing_key

        self._update_key_requirement_labels()

        layout.addStretch()

        footer = QLabel(
            "On macOS, your keys are stored in Apple Keychain.\n"
            "If Keychain is unavailable, Klaus falls back to ~/.klaus/config.toml."
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(footer)

        self._stack.addWidget(page)

    def _selected_key_slug(self) -> str:
        model = str(self._live_model_combo.currentData())
        return config.live_model_details(model)["provider"]

    def _on_live_model_changed(self) -> None:
        self._collected["live_model"] = str(self._live_model_combo.currentData())
        self._update_key_requirement_labels()
        self._update_next_enabled()

    def _update_key_requirement_labels(self) -> None:
        required = self._selected_key_slug()
        for label, slug, _prefix, _min_len in KEY_PATTERNS:
            suffix = " required" if slug == required else " optional"
            self._key_names[slug].setText(label + suffix)

    def _validate_key(self, slug: str) -> None:
        text = self._key_edits[slug].text().strip()
        indicator = self._key_indicators[slug]
        hint = self._key_hints[slug]

        if not text:
            existing_key = bool(self._collected.get(slug))
            indicator.setText("✓" if existing_key else "")
            if existing_key:
                indicator.setStyleSheet(
                    f"color: {theme.KLAUS_ACCENT}; font-size: 18px; "
                    "background: transparent; border: none;"
                )
            hint.setVisible(False)
            self._key_valid[slug] = existing_key
            self._update_next_enabled()
            return

        is_valid, message = validate_api_key(slug, text)
        if not is_valid:
            indicator.setText("✗")
            indicator.setStyleSheet(
                f"color: {theme.ERROR_COLOR}; font-size: 18px; "
                "background: transparent; border: none;"
            )
            hint.setText(message)
            hint.setVisible(bool(message))
            self._key_valid[slug] = False
        else:
            indicator.setText("✓")
            indicator.setStyleSheet(
                f"color: {theme.KLAUS_ACCENT}; font-size: 18px; "
                "background: transparent; border: none;"
            )
            hint.setVisible(False)
            self._key_valid[slug] = True
            self._collected[slug] = text

        self._update_next_enabled()

    # -- Step 6: About you (optional) --

    def _build_step_about_you(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(12)

        heading = QLabel("Tell Klaus about yourself")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        subtitle = QLabel(
            "This helps Klaus tailor explanations to your background.\n"
            "You can skip this or change it later in settings."
        )
        subtitle.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_BODY}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        self._background_edit = QPlainTextEdit()
        self._background_edit.setPlaceholderText(
            "e.g. I'm a software engineer interested in physics and philosophy. "
            "I have a strong math background but I'm new to biology."
        )
        self._background_edit.setFixedHeight(100)
        layout.addWidget(self._background_edit)

        layout.addSpacing(12)

        vault_header = QHBoxLayout()
        vault_label = QLabel("Obsidian vault path")
        vault_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
            "background: transparent; border: none;"
        )
        vault_header.addWidget(vault_label)

        help_btn = QPushButton("?")
        help_btn.setFixedSize(18, 18)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setToolTip(
            "Set your vault root, then ask Klaus: "
            "\"Save this to Folder/Note.md\" and it will create/append the note."
        )
        help_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.TEXT_SECONDARY}; "
            "border: none; padding: 0px; font-weight: bold; font-size: 14px; }\n"
            f"QPushButton:hover {{ color: {theme.KLAUS_ACCENT}; }}"
        )
        help_btn.clicked.connect(self._show_vault_help)
        vault_header.addWidget(help_btn)
        vault_header.addStretch()
        layout.addLayout(vault_header)

        vault_row = QHBoxLayout()
        self._vault_path_edit = QLineEdit()
        self._vault_path_edit.setReadOnly(True)
        self._vault_path_edit.setPlaceholderText("Optional. Click Browse to select")
        vault_row.addWidget(self._vault_path_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_vault_path)
        vault_row.addWidget(browse_btn)
        layout.addLayout(vault_row)

        skip_btn = QPushButton("Skip")
        skip_btn.setObjectName("wizard-link-btn")
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setFixedWidth(60)
        skip_btn.clicked.connect(lambda: self._set_step(NUM_STEPS - 1))
        layout.addWidget(skip_btn, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addStretch()
        self._stack.addWidget(page)

    def _browse_vault_path(self) -> None:
        """Open a native folder picker for the Obsidian vault directory."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Obsidian Vault Folder",
        )
        if path:
            self._vault_path_edit.setText(path)

    def _show_vault_help(self) -> None:
        """Show an informational dialog explaining the Obsidian vault setting."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Obsidian Notes")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "Set this to your Obsidian vault root folder.\n\n"
            "Then ask Klaus to save to a file in a folder, for example:\n"
            "  \"Save this to Research/Agent Notes.md\"\n\n"
            "Klaus will create missing folders/files and append the note.\n\n"
            "Leave this blank if you do not use Obsidian."
        )
        msg.exec()

    # -- Step 7: Done --

    def _build_step_done(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        heading = QLabel("You're all set.")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        toggle_hint = config.TOGGLE_KEY
        if config.PUSH_TO_TALK_KEY == config.TOGGLE_KEY and len(config.TOGGLE_KEY) == 1:
            toggle_hint = f"Shift+{config.TOGGLE_KEY}"
        instructions = QLabel(
            f"Hold {config.PUSH_TO_TALK_KEY} to talk. "
            f"Press {toggle_hint} to switch to hands-free mode.\n"
            "Choose a reading source when you need visual context. "
            "Name a vault note when you want to save."
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_BODY}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(instructions)

        layout.addSpacing(24)

        btn = QPushButton("Start using Klaus")
        btn.setObjectName("wizard-primary-btn")
        btn.setFixedWidth(220)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._finish_setup)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._stack.addWidget(page)
