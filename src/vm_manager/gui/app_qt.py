#!/usr/bin/env python3
"""
NeuronVM Manager - Qt-based VM Manager for NeuronOS.

Manages Windows/macOS VMs with GPU passthrough using PyQt6.
"""
from __future__ import annotations

import sys
import logging
from typing import Optional, List
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFrame,
    QProgressBar, QStatusBar, QMessageBox, QTabWidget,
    QGroupBox, QFormLayout, QComboBox, QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QColor

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from vm_manager.core.libvirt_manager import LibvirtManager, VMInfo, VMState
except ImportError as e:
    print(f"Warning: Could not import libvirt_manager: {e}")
    LibvirtManager = None

logger = logging.getLogger(__name__)


class VMCard(QFrame):
    """Card widget displaying a VM."""

    def __init__(self, vm_info, on_action):
        super().__init__()
        self.vm_info = vm_info
        self.on_action = on_action

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            VMCard {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 12px;
            }
            VMCard:hover {
                border-color: #0078d4;
            }
        """)

        layout = QHBoxLayout(self)

        # VM info
        info_layout = QVBoxLayout()

        name_label = QLabel(vm_info.name)
        name_label.setFont(QFont("", 14, QFont.Weight.Bold))
        name_label.setStyleSheet("color: white;")
        info_layout.addWidget(name_label)

        # Status
        status_text = "Running" if vm_info.state == VMState.RUNNING else "Stopped"
        status_color = "#4caf50" if vm_info.state == VMState.RUNNING else "#888888"
        status_label = QLabel(f"Status: {status_text}")
        status_label.setStyleSheet(f"color: {status_color};")
        info_layout.addWidget(status_label)

        # GPU info
        if vm_info.has_gpu_passthrough:
            gpu_label = QLabel("GPU Passthrough Enabled")
            gpu_label.setStyleSheet("color: #ff9800;")
            info_layout.addWidget(gpu_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # Action buttons
        btn_layout = QVBoxLayout()

        if vm_info.state == VMState.RUNNING:
            stop_btn = QPushButton("Stop")
            stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #d32f2f;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background-color: #f44336; }
            """)
            stop_btn.clicked.connect(lambda: self.on_action("stop", vm_info))
            btn_layout.addWidget(stop_btn)
        else:
            start_btn = QPushButton("Start")
            start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4caf50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background-color: #66bb6a; }
            """)
            start_btn.clicked.connect(lambda: self.on_action("start", vm_info))
            btn_layout.addWidget(start_btn)

        layout.addLayout(btn_layout)


class CreateVMWidget(QWidget):
    """Widget for creating new VMs."""

    def __init__(self, manager: Optional[LibvirtManager] = None):
        super().__init__()
        self.manager = manager

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Create New Virtual Machine")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        layout.addWidget(title)

        # Form
        form = QGroupBox("VM Configuration")
        form.setStyleSheet("""
            QGroupBox {
                color: white;
                border: 1px solid #404040;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        form_layout = QFormLayout(form)

        # OS Type
        self.os_combo = QComboBox()
        self.os_combo.addItems(["Windows 11", "Windows 10", "macOS Sonoma"])
        self.os_combo.setStyleSheet("background-color: #2d2d2d; color: white; padding: 8px;")
        form_layout.addRow("Operating System:", self.os_combo)

        # RAM
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(2, 128)
        self.ram_spin.setValue(8)
        self.ram_spin.setSuffix(" GB")
        self.ram_spin.setStyleSheet("background-color: #2d2d2d; color: white; padding: 8px;")
        form_layout.addRow("Memory:", self.ram_spin)

        # CPU Cores
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 32)
        self.cpu_spin.setValue(4)
        self.cpu_spin.setStyleSheet("background-color: #2d2d2d; color: white; padding: 8px;")
        form_layout.addRow("CPU Cores:", self.cpu_spin)

        # Disk Size
        self.disk_spin = QSpinBox()
        self.disk_spin.setRange(20, 2000)
        self.disk_spin.setValue(64)
        self.disk_spin.setSuffix(" GB")
        self.disk_spin.setStyleSheet("background-color: #2d2d2d; color: white; padding: 8px;")
        form_layout.addRow("Disk Size:", self.disk_spin)

        # GPU Passthrough
        self.gpu_check = QCheckBox("Enable GPU Passthrough")
        self.gpu_check.setStyleSheet("color: white;")
        form_layout.addRow("", self.gpu_check)

        layout.addWidget(form)

        # Create button
        create_btn = QPushButton("Create VM")
        create_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1084d8; }
        """)
        create_btn.clicked.connect(self._on_create)
        layout.addWidget(create_btn)

        layout.addStretch()

    def _on_create(self):
        if not self.manager:
            QMessageBox.critical(self, "Error", "Libvirt manager not available.")
            return

        name = f"Neuron-{self.os_combo.currentText().replace(' ', '-')}"
        ram = self.ram_spin.value()
        cpu = self.cpu_spin.value()
        disk = self.disk_spin.value()
        gpu = self.gpu_check.isChecked()

        # Simple confirmation
        confirm = QMessageBox.question(
            self, "Confirm Creation",
            f"Create {name} with:\n"
            f"- {ram}GB RAM\n"
            f"- {cpu} Cores\n"
            f"- {disk}GB Disk\n"
            f"- GPU Passthrough: {'Yes' if gpu else 'No'}\n\n"
            "This will create a new virtual disk. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.No:
            return

        # Disable button during creation
        self.sender().setEnabled(False)
        self.sender().setText("Creating...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            success = self.manager.create_windows_vm(
                name=name,
                ram_gb=ram,
                cpu_cores=cpu,
                disk_gb=disk,
                gpu_passthrough=gpu
            )

            if success:
                QMessageBox.information(self, "Success", f"Successfully created VM: {name}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to create VM. Check logs for details.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
        finally:
            self.sender().setEnabled(True)
            self.sender().setText("Create VM")
            QApplication.restoreOverrideCursor()


class NeuronVMWindow(QMainWindow):
    """Main NeuronVM Manager window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeuronVM Manager")
        self.setMinimumSize(900, 600)

        # Dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QLabel {
                color: white;
            }
            QTabWidget::pane {
                border: 1px solid #404040;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: white;
                padding: 10px 20px;
                border: 1px solid #404040;
            }
            QTabBar::tab:selected {
                background-color: #0078d4;
            }
        """)

        self.manager = None
        if LibvirtManager:
            self.manager = LibvirtManager()
            self.manager.connect()

        self._build_ui()
        self._load_vms()

        # Refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._load_vms)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: #2d2d2d; padding: 12px;")
        header_layout = QHBoxLayout(header)

        title = QLabel("NeuronVM Manager")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        header_layout.addWidget(title)

        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #505050; }
        """)
        refresh_btn.clicked.connect(self._load_vms)
        header_layout.addWidget(refresh_btn)

        layout.addWidget(header)

        # Tabs
        tabs = QTabWidget()

        # VMs tab
        self.vms_widget = QWidget()
        self.vms_layout = QVBoxLayout(self.vms_widget)
        self.vms_layout.setSpacing(12)
        self.vms_layout.setContentsMargins(16, 16, 16, 16)
        tabs.addTab(self.vms_widget, "Virtual Machines")

        # Create tab
        create_widget = CreateVMWidget(self.manager)
        tabs.addTab(create_widget, "Create New")

        layout.addWidget(tabs)

        # Status bar
        self.status = QStatusBar()
        self.status.setStyleSheet("background-color: #2d2d2d; color: #888888;")
        self.setStatusBar(self.status)

    def _load_vms(self):
        # Clear existing
        while self.vms_layout.count():
            item = self.vms_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.manager:
            no_libvirt = QLabel("libvirt not available. Please ensure libvirtd is running:\n\nsudo systemctl start libvirtd")
            no_libvirt.setStyleSheet("color: #ff9800; font-size: 14px;")
            self.vms_layout.addWidget(no_libvirt)
            self.vms_layout.addStretch()
            self.status.showMessage("libvirt not connected")
            return

        vms = self.manager.list_vms()

        if not vms:
            no_vms = QLabel("No virtual machines found.\n\nGo to 'Create New' tab to create a Windows or macOS VM.")
            no_vms.setStyleSheet("color: #888888; font-size: 14px;")
            self.vms_layout.addWidget(no_vms)
        else:
            for vm in vms:
                card = VMCard(vm, self._on_vm_action)
                self.vms_layout.addWidget(card)

        self.vms_layout.addStretch()
        self.status.showMessage(f"{len(vms)} virtual machines")

    def _on_vm_action(self, action: str, vm_info):
        if not self.manager:
            return

        if action == "start":
            success = self.manager.start_vm(vm_info.name)
            if success:
                self.status.showMessage(f"Starting {vm_info.name}...")
            else:
                QMessageBox.warning(self, "Error", f"Failed to start {vm_info.name}")
        elif action == "stop":
            success = self.manager.stop_vm(vm_info.name)
            if success:
                self.status.showMessage(f"Stopping {vm_info.name}...")
            else:
                QMessageBox.warning(self, "Error", f"Failed to stop {vm_info.name}")

        # Refresh after action
        QTimer.singleShot(1000, self._load_vms)

    def closeEvent(self, event):
        if self.manager:
            self.manager.disconnect()
        event.accept()


def main():
    """Entry point for NeuronVM Manager Qt version."""
    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("NeuronVM Manager")

    window = NeuronVMWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
