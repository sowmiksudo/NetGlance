import json
import logging
import urllib.request
import urllib.error
from typing import Any, Callable, Dict

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox, QHBoxLayout
)

from netspeedtray import constants
import netspeedtray

class UpdateCheckThread(QThread):
    result = pyqtSignal(bool, str, str)  # success, latest_version, download_url or error message
    
    def run(self):
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/sowmiksudo/NetGlance/releases/latest",
                headers={'User-Agent': 'NetGlance'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    latest_version = data.get("tag_name", "")
                    if latest_version.startswith("v"):
                        latest_version = latest_version[1:]
                    html_url = data.get("html_url", "")
                    self.result.emit(True, latest_version, html_url)
                else:
                    self.result.emit(False, "", "Failed to reach GitHub API.")
        except Exception as e:
            self.result.emit(False, "", str(e))


class AboutPage(QWidget):
    """About page for application info and updates."""

    def __init__(self, i18n, schedule_update_callback: Callable[[], None], parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.schedule_update = schedule_update_callback
        self.logger = logging.getLogger(f"NetSpeedTray.{self.__class__.__name__}")
        self.setup_ui()
        self._update_thread = None

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        title = QLabel(f"About NetGlance")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        author_label = QLabel("Author: Shayer Mahmud Sowmik")
        
        repo_layout = QHBoxLayout()
        repo_label = QLabel("Repository:")
        repo_link = QLabel('<a href="https://github.com/sowmiksudo/NetGlance">https://github.com/sowmiksudo/NetGlance</a>')
        repo_link.setOpenExternalLinks(True)
        repo_layout.addWidget(repo_label)
        repo_layout.addWidget(repo_link)
        repo_layout.addStretch()

        # Privacy Policy link (required by Microsoft Store Policy 10.5.1)
        privacy_layout = QHBoxLayout()
        privacy_label = QLabel("Privacy Policy:")
        privacy_link = QLabel('<a href="https://github.com/sowmiksudo/NetGlance/blob/main/PRIVACY_POLICY.md">View Privacy Policy</a>')
        privacy_link.setOpenExternalLinks(True)
        privacy_layout.addWidget(privacy_label)
        privacy_layout.addWidget(privacy_link)
        privacy_layout.addStretch()

        # License link
        license_layout = QHBoxLayout()
        license_label = QLabel("License:")
        license_link = QLabel('<a href="https://github.com/sowmiksudo/NetGlance/blob/main/LICENSE">GNU General Public License v3.0</a>')
        license_link.setOpenExternalLinks(True)
        license_layout.addWidget(license_label)
        license_layout.addWidget(license_link)
        license_layout.addStretch()

        license_note = QLabel("NetGlance is free and open-source software distributed under the GPLv3 license.")
        license_note.setWordWrap(True)
        license_note.setStyleSheet("color: #888888; font-size: 11px;")

        # Donate / Sponsor
        donate_layout = QHBoxLayout()
        donate_label = QLabel("Support:")
        self.donate_btn = QPushButton("☕  Donate / Sponsor")
        self.donate_btn.setMaximumWidth(200)
        self.donate_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #2ea043; color: white; border: none;"
            "  border-radius: 6px; padding: 6px 16px; font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #3fb950; }"
        )
        self.donate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.donate_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://sowmik.pages.dev/donate"))
        )
        donate_layout.addWidget(donate_label)
        donate_layout.addWidget(self.donate_btn)
        donate_layout.addStretch()

        version_label = QLabel(f"Current Version: {netspeedtray.__version__}")
        
        self.check_update_btn = QPushButton("Check for Updates")
        self.check_update_btn.clicked.connect(self.check_for_updates)
        self.check_update_btn.setMaximumWidth(200)

        layout.addWidget(title)
        layout.addWidget(author_label)
        layout.addLayout(repo_layout)
        layout.addLayout(privacy_layout)
        layout.addLayout(license_layout)
        layout.addWidget(license_note)
        layout.addLayout(donate_layout)
        layout.addWidget(version_label)
        layout.addWidget(self.check_update_btn)
        layout.addStretch()

    def check_for_updates(self):
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("Checking...")
        
        self._update_thread = UpdateCheckThread()
        self._update_thread.result.connect(self.on_update_check_result)
        self._update_thread.start()

    def on_update_check_result(self, success: bool, latest_version: str, url_or_err: str):
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("Check for Updates")
        
        if success:
            current = netspeedtray.__version__
            # simple string comparison, ideally semantic versioning comparison
            if latest_version != current and latest_version > current:
                msg = f"A new version ({latest_version}) is available!\n\nDo you want to download it?"
                reply = QMessageBox.question(self, "Update Available", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl(url_or_err))
            else:
                QMessageBox.information(self, "Up to date", "You are using the latest version of NetGlance.")
        else:
            QMessageBox.warning(self, "Update Check Failed", f"Could not check for updates:\n{url_or_err}")

    def load_settings(self, config: Dict[str, Any]):
        pass

    def get_settings(self) -> Dict[str, Any]:
        return {}
