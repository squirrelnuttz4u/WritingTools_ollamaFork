import json
import os
import sys

import darkdetect
from PySide6 import QtGui, QtCore, QtWidgets
from PySide6.QtGui import QImage, QPixmap


# ---------------------------------------------------------------------------
# Resource path resolution
#
# Every shipped resource (icons/, options.json, config.json, acnr_logo.png,
# the gradient backgrounds) lives next to the running exe (in production) or
# next to main.py (in dev). `app_dir()` is NOT reliable -
# Windows can pass an unqualified `argv[0]` (e.g. `"ACNR Intelligence.exe"`)
# when launched from autostart or via certain shell handlers, in which case
# dirname() returns "" and lookups silently fall back to the cwd.
#
# That's exactly the failure mode where the tray icon goes missing on
# Windows (QSystemTrayIcon constructed without a valid icon doesn't render).
# Always use app_dir() instead of sys.argv[0] for resource resolution.
# ---------------------------------------------------------------------------
def app_dir() -> str:
    """Absolute path to the directory holding the exe (frozen) or main.py (dev)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


# ---------------------------------------------------------------------------
# Theme resolution (runs at import time - BEFORE any UI module captures
# `colorMode` via `from ui.UIUtils import colorMode`).
#
# Supported themes:
#   acnr    - ACNR brand: near-white bg, dark-grey text, red accents. Default.
#   dark    - Pure dark: near-black bg, white text, ACNR-red accents kept.
#   gradient- Legacy: the upstream gradient background; follows OS dark mode.
#   plain   - Legacy: solid neutral grey; follows OS dark mode.
# ---------------------------------------------------------------------------
_CONFIG_PATH = os.path.join(app_dir(), 'config.json')
try:
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as _f:
        theme = (json.load(_f).get('theme') or 'acnr').lower()
except (OSError, ValueError):
    theme = 'acnr'

if theme == 'dark':
    colorMode = 'dark'
elif theme == 'acnr':
    colorMode = 'light'
else:
    # gradient / plain / anything else -> follow the OS
    colorMode = 'dark' if darkdetect.isDark() else 'light'


# Brand accent used by primary buttons (Send, Save, update-available link).
# ACNR red is kept on both the acnr and dark themes so branding stays
# consistent; the legacy themes fall back to the upstream green.
if theme in ('acnr', 'dark'):
    ACCENT       = '#b22222'   # ACNR firebrick red
    ACCENT_HOVER = '#8b1a1a'   # darker on hover
else:
    ACCENT       = '#2e7d32' if colorMode == 'dark' else '#4CAF50'
    ACCENT_HOVER = '#1b5e20' if colorMode == 'dark' else '#45a049'


class UIUtils:
    @classmethod
    def clear_layout(cls, layout):
        """
        Clear the layout of all widgets.
        """
        while ((child := layout.takeAt(0)) != None):
            # If the child is a layout, delete it
            if child.layout():
                cls.clear_layout(child.layout())
                child.layout().deleteLater()
            else:
                child.widget().deleteLater()

    @classmethod
    def resize_and_round_image(cls, image, image_size=100, rounding_amount=50):
        image = image.scaledToWidth(image_size)
        clipPath = QtGui.QPainterPath()
        clipPath.addRoundedRect(0, 0, image_size, image_size, rounding_amount, rounding_amount)
        target = QImage(image_size, image_size, QImage.Format_ARGB32)
        target.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(target)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setClipPath(clipPath)
        painter.drawImage(0, 0, image)
        painter.end()
        targetPixmap = QPixmap.fromImage(target)
        return targetPixmap

    @classmethod
    def setup_window_and_layout(cls, base: QtWidgets.QWidget):
        # Set the window icon
        icon_path = os.path.join(app_dir(), 'icons', 'app_icon.png')
        if os.path.exists(icon_path):
            base.setWindowIcon(QtGui.QIcon(icon_path))
        main_layout = QtWidgets.QVBoxLayout(base)
        main_layout.setContentsMargins(0, 0, 0, 0)
        base.background = ThemeBackground(base, theme)
        main_layout.addWidget(base.background)


class ThemeBackground(QtWidgets.QWidget):
    """
    Custom background widget. Renders per-theme:
      acnr     - near-white fill with a thin red top-stripe
      dark     - solid dark grey
      gradient - legacy gradient PNG from the upstream project
      plain    - solid neutral grey (light or dark per colorMode)
    """

    def __init__(self, parent=None, theme='acnr', is_popup=False, border_radius=0):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.theme = theme
        self.is_popup = is_popup
        self.border_radius = border_radius

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)

        # Clip to rounded rect so every theme respects border_radius.
        path = QtGui.QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(),
                            self.border_radius, self.border_radius)
        painter.setClipPath(path)

        if self.theme == 'acnr':
            # Near-white background with a subtle red accent stripe at the top.
            painter.fillRect(self.rect(), QtGui.QColor('#fafafa'))
            stripe_h = 6
            painter.fillRect(
                QtCore.QRect(0, 0, self.width(), stripe_h),
                QtGui.QColor('#b22222'),
            )
            return

        if self.theme == 'dark':
            painter.fillRect(self.rect(), QtGui.QColor(35, 35, 35))
            stripe_h = 6
            painter.fillRect(
                QtCore.QRect(0, 0, self.width(), stripe_h),
                QtGui.QColor('#b22222'),
            )
            return

        if self.theme == 'gradient':
            img_name = (
                'background_popup_dark.png' if self.is_popup and colorMode == 'dark'
                else 'background_popup.png' if self.is_popup
                else 'background_dark.png' if colorMode == 'dark'
                else 'background.png'
            )
            background_image = QtGui.QPixmap(
                os.path.join(app_dir(), img_name)
            )
            painter.drawPixmap(self.rect(), background_image)
            return

        # 'plain' and any unknown theme
        if colorMode == 'dark':
            color = QtGui.QColor(35, 35, 35)
        else:
            color = QtGui.QColor(222, 222, 222)
        painter.fillRect(self.rect(), color)
