#!/usr/bin/env python3
"""
Always-on-top Note Overlay (PyQt6)

- Frameless, translucent window
- Always on top
- Movable by dragging the title area
- Text edit with autosave to ~/.overlay_notes.txt
- Optional click-through toggle on Windows (uses ctypes)
"""

import sys
import os
from pathlib import Path
from PyQt6 import QtWidgets, QtGui, QtCore

# Optional Windows click-through support (WS_EX_LAYERED + WS_EX_TRANSPARENT)
IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    SetWindowLong = user32.SetWindowLongW
    GetWindowLong = user32.GetWindowLongW
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000
    LWA_ALPHA = 0x00000002


DEFAULT_SAVE = Path.home() / ".overlay_notes.txt"


class OverlayWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        # Window flags: frameless, stay on top, tool (so it doesn't show in taskbar on some platforms)
        flags = (
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)

        # Allow translucent background
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Quick Notes Overlay")

        # Default size & geometry
        self.resize(600, 320)
        self.move(50, 50)

        # State
        self._drag_pos = None
        self.always_on_top = True
        self.click_through = False

        # UI
        self._build_ui()

        # Autosave timer (create before connecting signals that may fire)
        self.autosave_timer = QtCore.QTimer(self)
        self.autosave_timer.setInterval(2000)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self._do_autosave)

        # Load saved notes
        self.load_notes(DEFAULT_SAVE)

        # Ensure keyboard focus
        self.text_edit.setFocus()


    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Title bar (drag area)
        title_bar = QtWidgets.QFrame()
        title_bar.setObjectName("title_bar")
        title_layout = QtWidgets.QHBoxLayout(title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)

        title_label = QtWidgets.QLabel("Quick Notes")
        title_label.setObjectName("title_label")
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Buttons
        self.pin_btn = QtWidgets.QPushButton("Pinned")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(True)
        self.pin_btn.clicked.connect(self.toggle_pinned)
        title_layout.addWidget(self.pin_btn)

        self.ct_btn = QtWidgets.QPushButton("Click-through")
        self.ct_btn.setCheckable(True)
        self.ct_btn.clicked.connect(self.toggle_click_through)
        title_layout.addWidget(self.ct_btn)

        copy_btn = QtWidgets.QPushButton("Copy")
        copy_btn.clicked.connect(self.copy_text)
        title_layout.addWidget(copy_btn)

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_text)
        title_layout.addWidget(clear_btn)

        layout.addWidget(title_bar)

        # Text edit area
        self.text_edit = QtWidgets.QPlainTextEdit()
        self.text_edit.setPlaceholderText("Type quick notes...")
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)

        # Footer
        footer = QtWidgets.QLabel("Drag the title bar to move. Double-click title to toggle pinned. Ctrl+S save.")
        footer.setObjectName("footer")
        layout.addWidget(footer)

        # Styling
        self.setStyleSheet(
            """
            QWidget {
                color: rgba(0,0,0,0.87);
                font-family: Inter, Arial, sans-serif;
            }
            #title_bar {
                background: rgba(190,225,230,0.6);
                border-radius: 10px;
            }
            #title_label {
                font-weight: 600;
                padding-left: 6px;
            }
            QPlainTextEdit {
                background: rgba(226,236,233,0.5);
                border-radius: 10px;
                padding: 10px;
                min-height: 160px;
                color: #E6EDF3;
                selection-background-color: rgba(79,70,229,0.6);
            }
            QPushButton {
                background: rgba(226,236,233,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                padding: 4px 8px;
                border-radius: 8px;
            }
            QPushButton:checked {
                background: rgba(79,70,229,0.16);
            }
            #footer {
                font-size: 11px;
                color: #AAB6C8;
                padding-left: 4px;
            }
            """
        )

    # --- drag behavior (title bar) ---
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        # Start dragging only from the title bar region (y <= 44px roughly)
        if event.button() == QtCore.Qt.MouseButton.LeftButton and event.position().y() <= 52:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        # double-click anywhere in top region toggles pinned state
        if event.position().y() <= 52:
            self.toggle_pinned()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    # --- text handlers & autosave ---
    def _on_text_changed(self):
        # reset the autosave timer on each change
        self.autosave_timer.start()

    def _do_autosave(self):
        try:
            self.save_notes(DEFAULT_SAVE)
            # feedback could be added (status, tray notification), omitted for simplicity
        except Exception as e:
            print("Autosave failed:", e)

    def save_notes(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            f.write(self.text_edit.toPlainText())

    def load_notes(self, path: Path):
        path = Path(path)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    self.text_edit.setPlainText(f.read())
            except Exception as e:
                print("Failed to load notes:", e)

    # --- buttons ---
    def toggle_pinned(self):
        self.always_on_top = not self.always_on_top
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, self.always_on_top)
        self.pin_btn.setText("Pinned" if self.always_on_top else "Unpinned")
        self.pin_btn.setChecked(self.always_on_top)
        # must call show() to make flag changes apply
        self.show()

    def toggle_click_through(self):
        # Click-through: on Windows, set WS_EX_TRANSPARENT to allow clicks to pass through.
        # Note: making window click-through will also make it impossible to interact with it
        # until click-through is turned off again (we provide button to toggle).
        self.click_through = not self.click_through
        self.ct_btn.setChecked(self.click_through)

        if IS_WINDOWS:
            hwnd = int(self.winId())  # QWidget.winId() -> platform-dependent handle
            exstyle = GetWindowLong(hwnd, GWL_EXSTYLE)
            if self.click_through:
                new = exstyle | WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                new = exstyle & ~WS_EX_TRANSPARENT
            SetWindowLong(hwnd, GWL_EXSTYLE, new)
        else:
            # Non-windows platforms: best-effort: set attribute to transparent for mouse events
            # Qt 6 supports setAttribute(Qt.WA_TransparentForMouseEvents) but that is per-widget.
            # Use it for our top-level widget (makes it non-interactive).
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, self.click_through)

        self.ct_btn.setText("Click-through" if not self.click_through else "Click-through (ON)")

    def copy_text(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())

    def clear_text(self):
        self.text_edit.clear()

    # --- keyboard shortcuts ---
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            if event.key() == QtCore.Qt.Key.Key_S:
                # Ctrl+S -> save immediately
                try:
                    self.save_notes(DEFAULT_SAVE)
                except Exception as e:
                    print("Save failed:", e)
                return
            elif event.key() == QtCore.Qt.Key.Key_O:
                # Ctrl+O -> open file dialog
                fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open notes file", str(Path.home()))
                if fn:
                    self.load_notes(Path(fn))
                return
        super().keyPressEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)

    # On macOS, set application menu and disable some window decorations quirks
    app.setWindowIcon(QtGui.QIcon())

    w = OverlayWindow()
    w.show()

    # Make window initially visible and on top
    w.raise_()
    w.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
