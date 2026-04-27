"""
Preview-before-replace window for rewrite actions.

The popup grid runs an action (Proofread / Professional / Concise / etc.)
and used to paste the model output straight over the user's selected text.
That meant a hallucinated edit silently destroyed the user's original. This
window inserts a confirmation step:

  +------------------------------------------+
  |  [logo]  Preview: Professional       [x] |
  |  ORIGINAL                                |
  |  [muted, read-only text view]            |
  |  PROFESSIONAL - REWRITE                  |
  |  [white, read-only text view]            |
  |  [Discard] [Regenerate] [Accept] (red)   |
  +------------------------------------------+

Keyboard:
  Esc       -> Discard
  Enter     -> Accept
  Ctrl+R    -> Regenerate
"""
from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ui.UIUtils import (
    ACCENT,
    ACCENT_HOVER,
    ThemeBackground,
    app_dir,
    colorMode,
    theme,
)


class PreviewWindow(QtWidgets.QWidget):
    """Confirm-before-replace dialog for rewrite-style actions."""

    accepted = Signal(str)        # accepted text -> WritingToolApp pastes it
    regenerate = Signal()         # user wants a fresh rewrite

    def __init__(self, option_name: str, original: str, rewrite: str, parent=None):
        super().__init__(parent)
        self.option_name = option_name
        self.original = original
        self.rewrite = rewrite

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(f"ACNR Intelligence - {option_name}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.background = ThemeBackground(
            self, theme, is_popup=True, border_radius=10
        )
        main_layout.addWidget(self.background)

        content = QVBoxLayout(self.background)
        content.setContentsMargins(14, 12, 14, 14)
        content.setSpacing(8)

        content.addLayout(self._build_header())
        content.addWidget(self._caption("Original"))
        self.original_view = self._build_text_panel(original, muted=True)
        self.original_view.setMaximumHeight(110)
        content.addWidget(self.original_view)

        content.addWidget(
            self._caption(f"{option_name} - rewrite", accent=True)
        )
        self.rewrite_view = self._build_text_panel(rewrite, muted=False)
        content.addWidget(self.rewrite_view, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {'#bbb' if colorMode == 'dark' else '#666'}; "
            f"font-size: 11px; font-style: italic;"
        )
        self.status_label.hide()
        content.addWidget(self.status_label)

        content.addLayout(self._build_button_row())

        QShortcut(QKeySequence("Escape"), self, activated=self.close)
        QShortcut(QKeySequence("Return"), self, activated=self._on_accept)
        QShortcut(QKeySequence("Enter"), self, activated=self._on_accept)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_regenerate)

        self.resize(560, 440)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        logo_path = os.path.join(app_dir(), "acnr_logo.png")
        if os.path.exists(logo_path):
            logo_label = QLabel()
            logo_label.setPixmap(
                QtGui.QPixmap(logo_path).scaledToHeight(
                    36, Qt.SmoothTransformation
                )
            )
            logo_label.setStyleSheet("background: transparent;")
            header.addWidget(logo_label)

        title = QLabel(f"Preview: {self.option_name}")
        title.setStyleSheet(
            f"color: {ACCENT}; font-size: 16px; font-weight: 700;"
        )
        header.addWidget(title, 1)

        close_btn = QPushButton("×")
        close_btn.setToolTip("Discard (Esc)")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {'#fff' if colorMode == 'dark' else '#333'};
                font-size: 20px; font-weight: bold;
                border: none; border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {'#333' if colorMode == 'dark' else '#ebebeb'};
            }}
            """
        )
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        return header

    def _caption(self, text: str, accent: bool = False) -> QLabel:
        label = QLabel(text.upper())
        if accent:
            color = ACCENT
            weight = 700
        else:
            color = "#bbb" if colorMode == "dark" else "#666"
            weight = 600
        label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: {weight};"
            f" letter-spacing: 0.5px;"
        )
        return label

    def _build_text_panel(self, text: str, muted: bool) -> QTextEdit:
        view = QTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setStyleSheet(self._panel_style(muted))
        return view

    def _panel_style(self, muted: bool) -> str:
        if muted:
            bg = "#2a2a2a" if colorMode == "dark" else "#f0f0f0"
            fg = "#bbb" if colorMode == "dark" else "#555"
        else:
            bg = "#1f1f1f" if colorMode == "dark" else "white"
            fg = "#fff" if colorMode == "dark" else "#222"
        border = "#555" if colorMode == "dark" else "#ddd"
        return (
            f"QTextEdit {{"
            f" background: {bg};"
            f" color: {fg};"
            f" border: 1px solid {border};"
            f" border-radius: 6px;"
            f" padding: 8px;"
            f" font-size: 13px;"
            f" }}"
        )

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)

        discard = QPushButton("Discard")
        discard.setToolTip("Close without changing your text (Esc)")
        discard.setStyleSheet(self._secondary_btn_style())
        discard.clicked.connect(self.close)
        row.addWidget(discard)

        self.regen_btn = QPushButton("Regenerate")
        self.regen_btn.setToolTip(
            "Ask the model for a different rewrite (Ctrl+R)"
        )
        self.regen_btn.setStyleSheet(self._secondary_btn_style())
        self.regen_btn.clicked.connect(self._on_regenerate)
        row.addWidget(self.regen_btn)

        self.accept_btn = QPushButton("Accept and replace")
        self.accept_btn.setToolTip(
            "Replace the selected text with the rewrite (Enter)"
        )
        self.accept_btn.setStyleSheet(self._primary_btn_style())
        self.accept_btn.setDefault(True)
        self.accept_btn.setAutoDefault(True)
        self.accept_btn.clicked.connect(self._on_accept)
        row.addWidget(self.accept_btn)
        return row

    def _primary_btn_style(self) -> str:
        return (
            f"QPushButton {{"
            f" background-color: {ACCENT};"
            f" color: white;"
            f" font-weight: 700;"
            f" padding: 8px 16px;"
            f" border: none;"
            f" border-radius: 6px;"
            f" min-width: 150px;"
            f" }}"
            f" QPushButton:hover {{ background-color: {ACCENT_HOVER}; }}"
            f" QPushButton:disabled {{ background-color: #888; color: #ddd; }}"
        )

    def _secondary_btn_style(self) -> str:
        bg = "#333" if colorMode == "dark" else "#e8e8e8"
        bg_hover = "#444" if colorMode == "dark" else "#dcdcdc"
        fg = "#fff" if colorMode == "dark" else "#333"
        border = "#555" if colorMode == "dark" else "#ccc"
        return (
            f"QPushButton {{"
            f" background-color: {bg};"
            f" color: {fg};"
            f" padding: 8px 16px;"
            f" border: 1px solid {border};"
            f" border-radius: 6px;"
            f" min-width: 100px;"
            f" }}"
            f" QPushButton:hover {{ background-color: {bg_hover}; }}"
            f" QPushButton:disabled {{ color: #999; }}"
        )

    # ------------------------------------------------------------------
    # Slots / actions
    # ------------------------------------------------------------------
    def _on_accept(self):
        self.accepted.emit(self.rewrite_view.toPlainText())
        self.close()

    def _on_regenerate(self):
        self.regen_btn.setEnabled(False)
        self.accept_btn.setEnabled(False)
        self.status_label.setText("Regenerating...")
        self.status_label.show()
        self.regenerate.emit()

    @Slot(str)
    def update_rewrite(self, new_text: str):
        """Called by WritingToolApp when a regenerated response arrives."""
        self.rewrite = new_text
        self.rewrite_view.setPlainText(new_text)
        self.regen_btn.setEnabled(True)
        self.accept_btn.setEnabled(True)
        self.status_label.hide()

    @Slot(str)
    def show_error(self, message: str):
        """Called by WritingToolApp when regeneration fails."""
        self.regen_btn.setEnabled(True)
        self.accept_btn.setEnabled(True)
        self.status_label.setStyleSheet(
            "color: #c0392b; font-size: 11px; font-weight: 600;"
        )
        self.status_label.setText(message)
        self.status_label.show()
