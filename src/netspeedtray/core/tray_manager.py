"""
Tray Icon Manager Module for NetSpeedTray.

This module encapsulates the logic for the application's system tray icon and
context menu. It handles icon loading, tray icon creation, menu creation,
and smart menu positioning.
"""

import os
import sys
import logging
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import QObject, QPoint, Qt, QRect
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QMenu, QApplication, QSystemTrayIcon, QWidget

from netspeedtray import constants
from netspeedtray.utils import styles as style_utils

if TYPE_CHECKING:
    from netspeedtray.views.widget import NetworkSpeedWidget
    from netspeedtray.constants.i18n import I18nStrings


class TrayIconManager(QObject):
    """
    Manages the system tray icon and context menu logic.
    """
    def __init__(self, parent_widget: 'NetworkSpeedWidget', i18n: 'I18nStrings'):
        super().__init__(parent_widget)
        self.widget = parent_widget
        self.i18n = i18n
        self.logger = logging.getLogger("NetSpeedTray.TrayIconManager")
        
        self.context_menu: Optional[QMenu] = None
        self.app_icon: Optional[QIcon] = None
        self.system_tray_icon: Optional[QSystemTrayIcon] = None
        
        # State tracking
        self.is_context_menu_visible: bool = False

        # Retrieve actions for external use if needed (e.g., toggling text)
        self.pause_action: Optional[QAction] = None

    def initialize(self) -> None:
        """Loads the icon, initializes the context menu, and creates the system tray icon."""
        self._load_and_set_icon()
        self._init_context_menu()
        self._init_system_tray_icon()

    def _load_and_set_icon(self) -> None:
        """
        Loads the application icon from resources and sets it on the parent widget.
        """
        try:
            # Determine base path for assets
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_path = sys._MEIPASS
            else:
                # Assuming this file is in src/netspeedtray/core/
                script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
                base_path = project_root

            icon_filename = constants.app.ICON_FILENAME
            icon_path = os.path.join(base_path, "assets", icon_filename)
            icon_path = os.path.normpath(icon_path)

            if os.path.exists(icon_path):
                self.app_icon = QIcon(icon_path)
                self.widget.setWindowIcon(self.app_icon)
                self.logger.debug("Application icon loaded and set successfully.")
            else:
                self.logger.warning("Application icon not found at '%s'. Using default system icon.", icon_path)
        except Exception as e:
            self.logger.error("Error loading application icon: %s", e, exc_info=True)

    def _init_context_menu(self) -> None:
        """Backbone for context menu creation."""
        self.logger.debug("Initializing context menu in manager...")
        try:
            self.context_menu = QMenu(self.widget)
            
            # Settings
            settings_action = self.context_menu.addAction(self.i18n.SETTINGS_MENU_ITEM)
            if hasattr(self.widget, 'show_settings'):
                settings_action.triggered.connect(self.widget.show_settings)
            
            self.context_menu.addSeparator()
            
            # Exit
            exit_action = self.context_menu.addAction(self.i18n.EXIT_MENU_ITEM)
            app_instance = QApplication.instance()
            if app_instance:
                # We connect to widget.close() usually, which handles cleanup
                exit_action.triggered.connect(self.widget.fully_exit_application)
            else:
                exit_action.setEnabled(False)
            
            self.logger.debug("Context menu initialized successfully.")
        except Exception as e:
            self.logger.error("Error initializing context menu: %s", e, exc_info=True)

    def _init_system_tray_icon(self) -> None:
        """
        Creates and shows the QSystemTrayIcon in the Windows notification area.
        This is the standard Windows convention for background/utility applications.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.logger.warning("System tray is not available on this platform. Skipping tray icon creation.")
            return

        try:
            self.system_tray_icon = QSystemTrayIcon(self.widget)

            # Set the icon — use the loaded app icon, or fall back to a default
            if self.app_icon and not self.app_icon.isNull():
                self.system_tray_icon.setIcon(self.app_icon)
            else:
                # Fallback: use the application's window icon
                app = QApplication.instance()
                if app and not app.windowIcon().isNull():
                    self.system_tray_icon.setIcon(app.windowIcon())
                self.logger.warning("No app icon available for system tray. Using application default.")

            # Set tooltip
            self.system_tray_icon.setToolTip(f"{constants.app.APP_NAME} v{constants.app.VERSION}")

            # Attach the same context menu used by right-click on the widget
            if self.context_menu:
                self.system_tray_icon.setContextMenu(self.context_menu)

            # Connect activation signals (single-click, double-click)
            self.system_tray_icon.activated.connect(self._on_tray_icon_activated)

            # Show the tray icon
            self.system_tray_icon.show()
            self.logger.debug("System tray icon created and shown successfully.")

        except Exception as e:
            self.logger.error("Failed to create system tray icon: %s", e, exc_info=True)

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """
        Handles activation of the system tray icon.
        
        - Double-click: Toggle the analytics dashboard (same as double-clicking the widget)
        - Single-click (Trigger): Toggle the analytics dashboard
        """
        try:
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                if hasattr(self.widget, 'toggle_analytics_dashboard'):
                    self.widget.toggle_analytics_dashboard()
            elif reason == QSystemTrayIcon.ActivationReason.Trigger:
                # Single left-click: toggle dashboard (standard Windows tray behavior)
                if hasattr(self.widget, 'toggle_analytics_dashboard'):
                    self.widget.toggle_analytics_dashboard()
        except Exception as e:
            self.logger.error("Error handling tray icon activation: %s", e, exc_info=True)

    def update_tooltip(self, upload_speed: str = "", download_speed: str = "") -> None:
        """
        Updates the system tray icon tooltip with current speed information.
        
        Args:
            upload_speed: Formatted upload speed string.
            download_speed: Formatted download speed string.
        """
        if self.system_tray_icon:
            try:
                if upload_speed and download_speed:
                    tooltip = f"{constants.app.APP_NAME}\n↑ {upload_speed}\n↓ {download_speed}"
                else:
                    tooltip = f"{constants.app.APP_NAME} v{constants.app.VERSION}"
                self.system_tray_icon.setToolTip(tooltip)
            except Exception as e:
                self.logger.error("Error updating tray tooltip: %s", e, exc_info=True)

    def show_context_menu(self) -> None:
        """
        Calculates position and shows the context menu.
        """
        if not self.context_menu:
            return

        try:
            menu_pos = self._calculate_menu_position()
            
            self.is_context_menu_visible = True
            if hasattr(self.widget, '_is_context_menu_visible'):
                self.widget._is_context_menu_visible = True

            self.context_menu.exec(menu_pos)
            
            self.is_context_menu_visible = False
            if hasattr(self.widget, '_is_context_menu_visible'):
                self.widget._is_context_menu_visible = False
            
            # Trigger visibility refresh on close, as per original logic
            if hasattr(self.widget, '_execute_refresh'):
                self.widget._execute_refresh() # Using internal method as it was in the original class
                
        except Exception as e:
            self.logger.error("Error showing context menu: %s", e, exc_info=True)

    def _calculate_menu_position(self) -> QPoint:
        """
        Calculates the optimal global position for the context menu.
        """
        try:
            # Access renderer from widget if available
            renderer = getattr(self.widget, 'renderer', None)
            text_rect_local = renderer.get_last_text_rect() if renderer else QRect()

            if not text_rect_local.isValid() or text_rect_local.isEmpty():
                ref_global_pos = self.widget.mapToGlobal(self.widget.rect().center())
                ref_top_global_y = self.widget.mapToGlobal(self.widget.rect().topLeft()).y()
            else:
                ref_global_pos = self.widget.mapToGlobal(text_rect_local.center())
                ref_top_global_y = self.widget.mapToGlobal(text_rect_local.topLeft()).y()

            menu_size = self.context_menu.sizeHint()
            menu_width = menu_size.width() if menu_size.width() > 0 else constants.ui.general.ESTIMATED_MENU_WIDTH
            menu_height = menu_size.height()

            target_x = ref_global_pos.x() - menu_width // 2
            target_y = ref_top_global_y - menu_height - constants.ui.general.MENU_PADDING_ABOVE
            target_pos = QPoint(int(round(target_x)), int(round(target_y)))

            screen = self.widget.screen() or QApplication.primaryScreen()
            if screen:
                screen_rect = screen.availableGeometry()
                validated_x = max(screen_rect.left(), min(target_pos.x(), screen_rect.right() - menu_width + 1))
                validated_y = max(screen_rect.top(), min(target_pos.y(), screen_rect.bottom() - menu_height + 1))
                target_pos.setX(validated_x)
                target_pos.setY(validated_y)
            
            return target_pos
        except Exception as e:
            self.logger.error("Error calculating menu position: %s", e, exc_info=True)
            return self.widget.mapToGlobal(self.widget.rect().center())

    def cleanup(self) -> None:
        """
        Hides and removes the system tray icon. Must be called during application shutdown
        to prevent ghost icons lingering in the notification area.
        """
        if self.system_tray_icon:
            try:
                self.system_tray_icon.hide()
                self.system_tray_icon.deleteLater()
                self.system_tray_icon = None
                self.logger.debug("System tray icon cleaned up.")
            except Exception as e:
                self.logger.error("Error cleaning up system tray icon: %s", e, exc_info=True)
