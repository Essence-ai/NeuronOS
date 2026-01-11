#!/usr/bin/env python3
"""
NeuronStore - Qt-based Application Store for NeuronOS.

A PyQt6 application that provides a unified interface for
installing applications across different compatibility layers.
"""
from __future__ import annotations

import sys
import logging
from typing import Optional, List
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea, QFrame,
    QListWidget, QProgressBar, QGridLayout,
    QSplitter, QStatusBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from store.app_catalog import (
    AppCatalog, AppInfo, AppCategory,
    CompatibilityLayer, CompatibilityRating
)
from store.installer import AppInstaller

logger = logging.getLogger(__name__)


class InstallWorker(QThread):
    """Background thread for app installation."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool)

    def __init__(self, installer: AppInstaller, app: AppInfo):
        super().__init__()
        self.installer = installer
        self.app = app

    def run(self):
        def callback(percent, message, status):
            self.progress.emit(percent, message)

        self.installer.set_progress_callback(callback)
        success = self.installer.install(self.app)
        self.finished.emit(success)


class AppCard(QFrame):
    """Card widget displaying an application."""

    def __init__(self, app: AppInfo, on_install):
        super().__init__()
        self.app = app
        self.on_install = on_install

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            AppCard {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 8px;
            }
            AppCard:hover {
                border-color: #0078d4;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header with name
        header = QHBoxLayout()

        name_label = QLabel(app.name)
        name_label.setFont(QFont("", 12, QFont.Weight.Bold))
        name_label.setStyleSheet("color: white;")
        header.addWidget(name_label)

        header.addStretch()

        # Rating
        rating_label = QLabel(self._get_rating_text())
        rating_label.setStyleSheet(f"color: {self._get_rating_color()};")
        header.addWidget(rating_label)

        layout.addLayout(header)

        # Publisher
        if app.publisher:
            pub_label = QLabel(app.publisher)
            pub_label.setStyleSheet("color: #888888; font-size: 10px;")
            layout.addWidget(pub_label)

        # Description
        desc_label = QLabel(app.description[:100] + "..." if len(app.description) > 100 else app.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout.addWidget(desc_label)

        # Layer indicator
        layer_label = QLabel(self._get_layer_text())
        layer_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(layer_label)

        # Install button
        self.install_btn = QPushButton("Install")
        self.install_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1084d8;
            }
            QPushButton:disabled {
                background-color: #404040;
                color: #888888;
            }
        """)
        self.install_btn.clicked.connect(self._on_install_clicked)
        layout.addWidget(self.install_btn)

        # Progress bar (hidden)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #404040;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
            }
        """)
        layout.addWidget(self.progress)

    def _get_rating_text(self) -> str:
        texts = {
            CompatibilityRating.PERFECT: "+++",
            CompatibilityRating.GOOD: "++",
            CompatibilityRating.PLAYABLE: "+",
            CompatibilityRating.RUNS: "~",
            CompatibilityRating.BROKEN: "X",
        }
        return texts.get(self.app.rating, "?")

    def _get_rating_color(self) -> str:
        colors = {
            CompatibilityRating.PERFECT: "#4caf50",
            CompatibilityRating.GOOD: "#8bc34a",
            CompatibilityRating.PLAYABLE: "#ffeb3b",
            CompatibilityRating.RUNS: "#ff9800",
            CompatibilityRating.BROKEN: "#f44336",
        }
        return colors.get(self.app.rating, "#888888")

    def _get_layer_text(self) -> str:
        layers = {
            CompatibilityLayer.NATIVE: "Native Linux",
            CompatibilityLayer.FLATPAK: "Flatpak",
            CompatibilityLayer.WINE: "Wine",
            CompatibilityLayer.PROTON: "Proton",
            CompatibilityLayer.VM_WINDOWS: "Windows VM",
            CompatibilityLayer.VM_MACOS: "macOS VM",
        }
        return layers.get(self.app.layer, "Unknown")

    def _on_install_clicked(self):
        self.on_install(self.app, self)

    def set_installing(self, installing: bool):
        self.install_btn.setEnabled(not installing)
        self.progress.setVisible(installing)
        if installing:
            self.install_btn.setText("Installing...")

    def set_progress(self, percent: int, text: str = ""):
        self.progress.setValue(percent)
        if text:
            self.progress.setFormat(text)

    def set_installed(self):
        self.install_btn.setText("Installed")
        self.install_btn.setEnabled(False)
        self.progress.setVisible(False)


class CategoryList(QListWidget):
    """Sidebar list for category navigation."""

    def __init__(self, on_category_selected):
        super().__init__()
        self.on_category_selected = on_category_selected

        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                color: white;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #333333;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QListWidget::item:hover {
                background-color: #333333;
            }
        """)

        # Add categories
        self.addItem("All Apps")
        self.addItem("---")  # Separator

        categories = [
            ("Productivity", AppCategory.PRODUCTIVITY),
            ("Creative", AppCategory.CREATIVE),
            ("Gaming", AppCategory.GAMING),
            ("Development", AppCategory.DEVELOPMENT),
            ("Communication", AppCategory.COMMUNICATION),
            ("Media", AppCategory.MEDIA),
            ("Utilities", AppCategory.UTILITIES),
        ]

        self._category_map = {0: None}  # "All Apps" -> None

        for i, (name, cat) in enumerate(categories):
            self.addItem(name)
            self._category_map[i + 2] = cat  # +2 for "All Apps" and separator

        self.addItem("---")  # Separator
        self.addItem("Native")
        self.addItem("Windows VM")

        self.currentRowChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self, row: int):
        if row in self._category_map:
            self.on_category_selected(self._category_map[row])


class NeuronStoreWindow(QMainWindow):
    """Main NeuronStore window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeuronStore")
        self.setMinimumSize(1000, 700)

        # Dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QLabel {
                color: white;
            }
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)

        self.catalog = AppCatalog()
        self.catalog.load()
        self.installer = AppInstaller()

        self._current_category: Optional[AppCategory] = None
        self._search_query: str = ""
        self._workers: List[InstallWorker] = []

        self._build_ui()
        self._load_apps()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("background-color: #2d2d2d;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        title = QLabel("NeuronStore")
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search apps...")
        self.search_box.setMinimumWidth(300)
        self.search_box.textChanged.connect(self._on_search_changed)
        header_layout.addWidget(self.search_box)

        main_layout.addWidget(header)

        # Content area
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar
        self.category_list = CategoryList(self._on_category_selected)
        self.category_list.setMaximumWidth(200)
        splitter.addWidget(self.category_list)

        # Apps grid area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #1e1e1e; }")

        self.apps_container = QWidget()
        self.apps_layout = QGridLayout(self.apps_container)
        self.apps_layout.setSpacing(16)
        self.apps_layout.setContentsMargins(16, 16, 16, 16)

        scroll.setWidget(self.apps_container)
        splitter.addWidget(scroll)

        splitter.setSizes([200, 800])
        main_layout.addWidget(splitter)

        # Status bar
        self.status = QStatusBar()
        self.status.setStyleSheet("background-color: #2d2d2d; color: #888888;")
        self.setStatusBar(self.status)

    def _load_apps(self, apps: Optional[List[AppInfo]] = None):
        # Clear existing
        while self.apps_layout.count():
            item = self.apps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if apps is None:
            apps = self.catalog.search(
                query=self._search_query,
                category=self._current_category
            )

        cols = 3
        for i, app in enumerate(apps):
            card = AppCard(app, self._on_install_app)
            self.apps_layout.addWidget(card, i // cols, i % cols)

        self.status.showMessage(f"{len(apps)} apps")

    def _on_search_changed(self, text: str):
        self._search_query = text
        self._load_apps()

    def _on_category_selected(self, category: Optional[AppCategory]):
        self._current_category = category
        self._load_apps()

    def _on_install_app(self, app: AppInfo, card: AppCard):
        card.set_installing(True)

        worker = InstallWorker(self.installer, app)
        worker.progress.connect(lambda p, m: card.set_progress(p, m))
        worker.finished.connect(lambda s: self._on_install_finished(card, s))
        self._workers.append(worker)
        worker.start()

    def _on_install_finished(self, card: AppCard, success: bool):
        if success:
            card.set_installed()
        else:
            card.set_installing(False)
            card.install_btn.setText("Retry")


def main():
    """Entry point for NeuronStore Qt version."""
    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("NeuronStore")

    window = NeuronStoreWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
