"""
AnalyticsDashboard — A macOS-style frameless network analytics panel.

This module provides a unified, floating analytics widget inspired by macOS
menu-bar popovers. It displays real-time network statistics in five stacked
sections: speed header, usage graph, connection details, interface info,
and active network processes.

All data is live, powered by psutil polling on background QThreads.
"""

import math
import socket
import subprocess
import time
import ctypes
from ctypes import wintypes, windll

import numpy as np
import psutil

from PyQt6.QtCore import (
    Qt, QPoint, QRectF, QTimer, QThread, pyqtSignal,
    QPropertyAnimation, QEasingCurve, QRect, QEvent
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QBrush, QPen,
    QLinearGradient, QRegion
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QGraphicsDropShadowEffect, QApplication,
    QSizePolicy, QPushButton
)
import pyqtgraph as pg


# ─── Design Tokens ────────────────────────────────────────────────────────────

_COLORS = {
    "bg":              "#1E1E1E",
    "bg_section":      "#2A2A2A",
    "separator":       "#3A3A3A",
    "text_primary":    "#FFFFFF",
    "text_secondary":  "#8E8E93",
    "text_tertiary":   "#636366",
    "upload":          "#FF3B30",
    "upload_fill":     "rgba(255, 59, 48, 0.25)",
    "download":        "#007AFF",
    "download_fill":   "rgba(0, 122, 255, 0.25)",
    "status_green":    "#30D158",
    "status_red":      "#FF453A",
    "accent":          "#0A84FF",
}

_FONT_FAMILY = '"SF Pro Display", "Segoe UI", "Helvetica Neue", sans-serif'

_PANEL_WIDTH = 360
_BORDER_RADIUS = 12
_H_PADDING = 18
_V_SPACING = 6
_GRAPH_POINTS = 60          # 60-second rolling window
_UPDATE_INTERVAL_MS = 1000  # 1-second refresh cycle


# ─── Taskbar Detection (standalone, no netspeedtray imports) ──────────────────

def _get_taskbar_rect():
    """
    Find the primary Windows taskbar rect using Win32 API.
    Returns (left, top, right, bottom) in physical pixels, or None.
    """
    try:
        import win32gui
        hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
        if hwnd:
            return win32gui.GetWindowRect(hwnd)
    except Exception:
        pass

    # Fallback via ctypes if pywin32 not available
    try:
        class APPBARDATA(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT),
                ("rc", wintypes.RECT),
                ("lParam", wintypes.LPARAM),
            ]

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(abd)
        windll.shell32.SHAppBarMessage(5, ctypes.byref(abd))  # ABM_GETTASKBARPOS = 5
        rc = abd.rc
        return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception:
        return None


# ─── Background Data Workers ─────────────────────────────────────────────────

class _NetworkSpeedWorker(QThread):
    """
    Polls psutil.net_io_counters() every second and emits
    (dl_speed_kbps, ul_speed_kbps, total_recv_bytes, total_sent_bytes).
    """
    data_ready = pyqtSignal(float, float, float, float)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        counters = psutil.net_io_counters()
        prev_recv = counters.bytes_recv
        prev_sent = counters.bytes_sent

        while self._running:
            time.sleep(1.0)
            if not self._running:
                break
            counters = psutil.net_io_counters()
            dl_bytes = counters.bytes_recv - prev_recv
            ul_bytes = counters.bytes_sent - prev_sent
            prev_recv = counters.bytes_recv
            prev_sent = counters.bytes_sent

            dl_kbps = dl_bytes / 1024.0
            ul_kbps = ul_bytes / 1024.0

            self.data_ready.emit(dl_kbps, ul_kbps, counters.bytes_recv, counters.bytes_sent)

    def stop(self):
        self._running = False
        self.wait(2000)


class _PingWorker(QThread):
    """
    Pings 8.8.8.8 every 2 seconds and emits (latency_ms, jitter_ms, is_connected).
    Uses subprocess ping to avoid needing raw socket privileges.
    """
    data_ready = pyqtSignal(float, float, bool)

    def __init__(self):
        super().__init__()
        self._running = True
        self._recent_pings = []

    def run(self):
        while self._running:
            try:
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "1500", "8.8.8.8"],
                    capture_output=True, text=True, timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                output = result.stdout

                # Parse latency from Windows ping output: "time=XXms" or "time<1ms"
                latency = -1.0
                for line in output.splitlines():
                    if "time=" in line.lower() or "time<" in line.lower():
                        import re
                        match = re.search(r'time[=<](\d+)', line, re.IGNORECASE)
                        if match:
                            latency = float(match.group(1))
                            break

                if latency >= 0:
                    self._recent_pings.append(latency)
                    if len(self._recent_pings) > 5:
                        self._recent_pings.pop(0)

                    jitter = 0.0
                    if len(self._recent_pings) >= 2:
                        diffs = [abs(self._recent_pings[i] - self._recent_pings[i-1])
                                 for i in range(1, len(self._recent_pings))]
                        jitter = sum(diffs) / len(diffs)

                    self.data_ready.emit(latency, jitter, True)
                else:
                    self.data_ready.emit(0.0, 0.0, False)

            except Exception:
                self.data_ready.emit(0.0, 0.0, False)

            # Sleep 2s in slices for responsive shutdown
            for _ in range(20):
                if not self._running:
                    return
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait(4000)


# ─── Helper Widgets ───────────────────────────────────────────────────────────

class _Separator(QFrame):
    """Thin horizontal line used to visually divide sections."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {_COLORS['separator']}; border: none;")


class _SectionTitle(QLabel):
    """Small uppercase section heading label."""

    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"color: {_COLORS['text_tertiary']}; "
            f"font-family: {_FONT_FAMILY}; "
            f"font-size: 10px; "
            f"font-weight: 600; "
            f"letter-spacing: 1px; "
            f"padding: 0px; margin: 0px;"
        )


# ─── Main Dashboard Widget ───────────────────────────────────────────────────

class AnalyticsDashboard(QWidget):
    """
    Frameless floating analytics panel inspired by macOS menu-bar popovers.

    Displays five vertically-stacked sections with real-time data:
        A. Current upload/download speeds
        B. 60-second rolling usage history area chart
        C. Connection details grid (totals, status, latency, jitter)
        D. Interface & address information
        E. Top network processes
    """

    # Emitted when user clicks the "Detailed Graph" button
    open_graph_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Window flags ──────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(_PANEL_WIDTH)

        # ── Drop shadow ──────────────────────────────────────────────────
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        # ── Data state ───────────────────────────────────────────────────
        self._dl_history = np.zeros(_GRAPH_POINTS)
        self._ul_history = np.zeros(_GRAPH_POINTS)
        self._current_dl = 0.0
        self._current_ul = 0.0
        self._proc_io_prev = {}      # {pid: (read_bytes, write_bytes, timestamp)}
        self._proc_last_refresh = 0  # time.time() of last process refresh

        # ── Build UI ─────────────────────────────────────────────────────
        self._build_ui()

        # ── Slide animation ──────────────────────────────────────────────
        self._slide_anim = QPropertyAnimation(self, b"geometry")
        self._slide_anim.setDuration(280)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # ── Start background workers ─────────────────────────────────────
        self._speed_worker = _NetworkSpeedWorker()
        self._speed_worker.data_ready.connect(self._on_speed_data)
        self._speed_worker.start()

        self._ping_worker = _PingWorker()
        self._ping_worker.data_ready.connect(self._on_ping_data)
        self._ping_worker.start()

        # ── Periodic UI refresh ──────────────────────────────────────────
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_processes)
        self._refresh_timer.start(3000)  # Refresh process list every 3s

        # ── Initial data (run synchronously so panel height is correct) ──
        self._populate_interface_info()
        self._refresh_processes()

        self._is_hiding = False
        self._show_time = 0.0  # Time when dashboard was shown

        # ── External data source tracking ─────────────────────────────────
        self._ext_prev_recv = None
        self._ext_prev_sent = None
        self._ext_prev_time = None

    # ── External data integration ──────────────────────────────────────

    def connect_to_app(self, monitor_thread):
        """
        Connect to the main app's NetworkMonitorThread for synchronized speed data.
        Stops the dashboard's own independent speed worker.
        """
        self._speed_worker.stop()
        monitor_thread.counters_ready.connect(self._on_external_counters)

    def _on_external_counters(self, counters_dict):
        """Process per-NIC counters from the main app's monitor thread."""
        now = time.time()
        total_recv = sum(c.bytes_recv for c in counters_dict.values())
        total_sent = sum(c.bytes_sent for c in counters_dict.values())

        if self._ext_prev_recv is not None:
            elapsed = now - self._ext_prev_time
            if elapsed > 0.1:
                dl_kbps = max(0, (total_recv - self._ext_prev_recv) / elapsed / 1024.0)
                ul_kbps = max(0, (total_sent - self._ext_prev_sent) / elapsed / 1024.0)
                self._on_speed_data(dl_kbps, ul_kbps, total_recv, total_sent)

        self._ext_prev_recv = total_recv
        self._ext_prev_sent = total_sent
        self._ext_prev_time = now

    # ── Public helpers ────────────────────────────────────────────────────

    def show_anchored(self):
        """
        Position the panel above the taskbar in the bottom-right corner,
        then show with a slide-up animation.
        """
        self.adjustSize()

        screen = QApplication.primaryScreen()
        if not screen:
            self.show()
            return

        screen_geo = screen.availableGeometry()
        taskbar_rect = _get_taskbar_rect()

        panel_w = self.width()
        panel_h = self.height()

        # Right-align with a small margin from the right edge
        x = screen_geo.right() - panel_w - 8

        if taskbar_rect:
            # Position just above the taskbar
            taskbar_top = taskbar_rect[1]
            dpi = screen.devicePixelRatio()
            taskbar_top_logical = int(taskbar_top / dpi) if dpi > 1 else taskbar_top
            y = taskbar_top_logical - panel_h - 8
        else:
            # Fallback: bottom of available geometry
            y = screen_geo.bottom() - panel_h - 8

        # Slide-up animation: start below final position
        start_rect = QRect(x, y + 30, panel_w, panel_h)
        end_rect = QRect(x, y, panel_w, panel_h)

        self.setGeometry(start_rect)
        self.show()

        self._slide_anim.setStartValue(start_rect)
        self._slide_anim.setEndValue(end_rect)
        self._slide_anim.start()

        # Encourage window to take focus
        self.raise_()
        self.activateWindow()

    def hide_animated(self):
        """Slide-down and hide."""
        if self._is_hiding:
            return
        self._is_hiding = True

        current = self.geometry()
        end_rect = QRect(current.x(), current.y() + 30, current.width(), current.height())

        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(current)
        anim.setEndValue(end_rect)
        anim.finished.connect(self._on_hide_finished)
        anim.start()
        # Store reference to prevent garbage collection
        self._hide_anim = anim

    def _on_hide_finished(self):
        """Called when slide-down animation completes."""
        self.hide()
        self._is_hiding = False

    # ── Events ────────────────────────────────────────────────────────────

    def changeEvent(self, event):
        """
        Auto-hide when the window loses activation (user clicks elsewhere).
        """
        if event.type() == QEvent.Type.ActivationChange:
            # Add a 1-second grace period after showing to prevent immediate close
            # if the window doesn't gain focus instantly.
            if not self.isActiveWindow() and self.isVisible() and (time.time() - self._show_time > 1.0):
                self.hide_animated()
        super().changeEvent(event)

    def showEvent(self, event):
        """Start the focus-check timer when dashboard becomes visible."""
        super().showEvent(event)
        self._show_time = time.time()
        if not hasattr(self, '_focus_timer'):
            self._focus_timer = QTimer(self)
            self._focus_timer.timeout.connect(self._check_foreground)
        self._focus_timer.start(300)

    def hideEvent(self, event):
        """Stop the focus-check timer when hidden."""
        if hasattr(self, '_focus_timer'):
            self._focus_timer.stop()
        super().hideEvent(event)

    def _check_foreground(self):
        """OS-level check: close dashboard if it's no longer the foreground window."""
        if not self.isVisible() or self._is_hiding:
            return
        # Add a 1-second grace period after showing
        if time.time() - self._show_time < 1.0:
            return
        try:
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
            my_hwnd = int(self.winId())
            if fg_hwnd != my_hwnd:
                self.hide_animated()
        except Exception:
            pass

    def closeEvent(self, event):
        """Clean up background threads."""
        self._speed_worker.stop()
        self._ping_worker.stop()
        self._refresh_timer.stop()
        super().closeEvent(event)

    def paintEvent(self, event):
        """Draw the rounded-rect dark background behind all child widgets."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        rect = QRectF(8, 4, self.width() - 16, self.height() - 12)
        path.addRoundedRect(rect, _BORDER_RADIUS, _BORDER_RADIUS)

        painter.fillPath(path, QColor(_COLORS["bg"]))
        painter.end()

    def resizeEvent(self, event):
        """Update the widget mask so clicks outside the rounded rect pass through."""
        super().resizeEvent(event)
        path = QPainterPath()
        rect = QRectF(8, 4, self.width() - 16, self.height() - 12)
        path.addRoundedRect(rect, _BORDER_RADIUS, _BORDER_RADIUS)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    # ── Data callbacks ────────────────────────────────────────────────────

    def _on_speed_data(self, dl_kbps, ul_kbps, total_recv, total_sent):
        """Called every second with fresh speed data from the worker thread."""
        self._current_dl = dl_kbps
        self._current_ul = ul_kbps

        # Roll history arrays
        self._dl_history = np.roll(self._dl_history, -1)
        self._dl_history[-1] = dl_kbps
        self._ul_history = np.roll(self._ul_history, -1)
        self._ul_history[-1] = ul_kbps

        # Update header — always in Mbps
        dl_mbps = dl_kbps * 8 / 1000
        ul_mbps = ul_kbps * 8 / 1000
        self._dl_value_label.setText(f"{dl_mbps:.2f} Mbps")
        self._ul_value_label.setText(f"{ul_mbps:.2f} Mbps")

        # Update graph
        x = np.arange(_GRAPH_POINTS)
        self._dl_curve.setData(x, self._dl_history)
        self._ul_curve.setData(x, self._ul_history)

        # Update totals
        self._total_dl_label.setText(self._format_bytes(total_recv))
        self._total_ul_label.setText(self._format_bytes(total_sent))

    def _on_ping_data(self, latency, jitter, connected):
        """Called every ~2 seconds with ping results."""
        if connected:
            self._status_label.setText("Connected")
            self._status_label.setStyleSheet(
                self._label_style(_COLORS["status_green"], 12, 600)
            )
            self._latency_label.setText(f"{latency:.0f} ms")
            self._jitter_label.setText(f"{jitter:.1f} ms")
        else:
            self._status_label.setText("Disconnected")
            self._status_label.setStyleSheet(
                self._label_style(_COLORS["status_red"], 12, 600)
            )
            self._latency_label.setText("— ms")
            self._jitter_label.setText("— ms")

    def _refresh_processes(self):
        """Refresh active network processes with proportional network speed estimates."""
        try:
            now = time.time()
            elapsed = now - self._proc_last_refresh if self._proc_last_refresh else 3.0
            elapsed = max(elapsed, 0.5)

            # 1. Collect PIDs with active network connections
            pid_names = {}  # {pid: process_name}
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "ESTABLISHED" and conn.pid:
                    if conn.pid in pid_names:
                        continue
                    try:
                        p = psutil.Process(conn.pid)
                        name = p.name()
                        if name.lower() not in ("system", "svchost.exe", ""):
                            pid_names[conn.pid] = name
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            # 2. Measure raw I/O deltas per PID
            proc_io_deltas = []  # [(name, io_delta_kbps)]
            new_io_prev = {}

            for pid, name in pid_names.items():
                try:
                    io = psutil.Process(pid).io_counters()
                    current_bytes = io.read_bytes + io.write_bytes
                    new_io_prev[pid] = (io.read_bytes, io.write_bytes, now)

                    if pid in self._proc_io_prev:
                        prev_r, prev_w, _ = self._proc_io_prev[pid]
                        delta_bytes = max(0, current_bytes - (prev_r + prev_w))
                        io_kbps = (delta_bytes / elapsed) / 1024.0
                    else:
                        io_kbps = 0.0

                    proc_io_deltas.append((name, io_kbps))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            self._proc_io_prev = new_io_prev
            self._proc_last_refresh = now

            # 3. Deduplicate by name (sum I/O for same-name processes)
            name_io = {}
            for name, io_kbps in proc_io_deltas:
                name_io[name] = name_io.get(name, 0.0) + io_kbps

            # 4. Proportional distribution of actual network speed
            #    io_counters() includes disk I/O, so raw values are inflated.
            #    We distribute the real total network speed proportionally
            #    based on each process's I/O share.
            total_net_speed = self._current_dl + self._current_ul  # Real network KB/s
            total_io = sum(name_io.values())

            sorted_procs = []
            for name, io_kbps in name_io.items():
                if total_io > 0 and total_net_speed > 0:
                    net_speed = (io_kbps / total_io) * total_net_speed
                else:
                    net_speed = 0.0
                sorted_procs.append((name, net_speed))

            sorted_procs.sort(key=lambda x: x[1], reverse=True)
            top5 = sorted_procs[:5]

            # 5. Update UI
            for i in range(5):
                if i < len(top5):
                    name, speed = top5[i]
                    self._proc_name_labels[i].setText(name)
                    self._proc_name_labels[i].setStyleSheet(
                        self._label_style(_COLORS["text_primary"], 12)
                    )
                    # Convert KB/s to Mbps: kbps * 8 / 1000
                    speed_mbps = (speed * 8) / 1000
                    self._proc_speed_labels[i].setText(f"{speed_mbps:.2f} Mbps")
                    self._proc_dot_labels[i].setStyleSheet(
                        f"color: {_COLORS['accent']}; font-size: 8px; padding-top: 2px;"
                    )
                else:
                    self._proc_name_labels[i].setText("—")
                    self._proc_name_labels[i].setStyleSheet(
                        self._label_style(_COLORS["text_tertiary"], 12)
                    )
                    self._proc_speed_labels[i].setText("")
                    self._proc_dot_labels[i].setStyleSheet(
                        f"color: {_COLORS['text_tertiary']}; font-size: 8px; padding-top: 2px;"
                    )

        except Exception:
            pass

    def _populate_interface_info(self):
        """One-shot lookup of the active network interface details."""
        try:
            # Find primary interface via default-route socket trick
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]

            iface_name = "Unknown"
            mac_addr = "—"

            addrs = psutil.net_if_addrs()
            for name, addr_list in addrs.items():
                for addr in addr_list:
                    if addr.family == socket.AF_INET and addr.address == local_ip:
                        iface_name = name
                        # Now find the MAC for this interface
                        for a in addr_list:
                            if a.family == psutil.AF_LINK:
                                mac_addr = a.address
                        break

            self._iface_name_label.setText(iface_name)
            self._mac_label.setText(mac_addr)
            self._ip_label.setText(local_ip)

        except Exception:
            self._iface_name_label.setText("No connection")
            self._mac_label.setText("—")
            self._ip_label.setText("—")

    # ── Formatting helpers ────────────────────────────────────────────────

    @staticmethod
    def _format_speed(kbps: float) -> str:
        """Format speed with auto-scaling: KB/s below 1 Mbps, Mbps at/above."""
        mbps = kbps * 8 / 1000
        if mbps >= 1.0:
            return f"{mbps:.2f} Mbps"
        return f"{kbps:.1f} KB/s"

    @staticmethod
    def _format_bytes(total_bytes: float) -> str:
        """Format total bytes into human-readable form."""
        if total_bytes >= 1024 ** 3:
            return f"{total_bytes / (1024 ** 3):.2f} GB"
        elif total_bytes >= 1024 ** 2:
            return f"{total_bytes / (1024 ** 2):.1f} MB"
        else:
            return f"{total_bytes / 1024:.0f} KB"

    @staticmethod
    def _label_style(color: str, size: int = 12, weight: int = 400) -> str:
        return (
            f"color: {color}; "
            f"font-family: {_FONT_FAMILY}; "
            f"font-size: {size}px; "
            f"font-weight: {weight}; "
            f"background: transparent; "
            f"padding: 0px; margin: 0px;"
        )

    # ── Internal UI construction ──────────────────────────────────────────

    def _build_ui(self):
        """Assemble all five sections inside a vertical layout."""
        root = QVBoxLayout(self)
        root.setContentsMargins(_H_PADDING + 8, 20, _H_PADDING + 8, 14)
        root.setSpacing(_V_SPACING)

        root.addLayout(self._build_header())
        root.addWidget(_Separator())
        root.addWidget(self._build_graph())
        root.addWidget(self._build_graph_button())
        root.addWidget(_Separator())
        root.addLayout(self._build_details_grid())
        root.addWidget(_Separator())
        root.addLayout(self._build_interface_grid())
        root.addWidget(_Separator())
        root.addLayout(self._build_processes())

    # ── Section A: Speed Header ───────────────────────────────────────────

    def _build_header(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 2, 0, 4)
        layout.setSpacing(8)

        # Download (left) — takes equal share of width
        dl_block = QVBoxLayout()
        dl_block.setSpacing(2)
        dl_label = self._make_label("●  Download", 10, _COLORS["download"], weight=500)
        self._dl_value_label = self._make_label("0.0 KB/s", 20, _COLORS["download"], weight=700)
        self._dl_value_label.setMinimumWidth(140)
        dl_block.addWidget(dl_label)
        dl_block.addWidget(self._dl_value_label)

        # Upload (right) — takes equal share of width
        ul_block = QVBoxLayout()
        ul_block.setSpacing(2)
        ul_label = self._make_label("●  Upload", 10, _COLORS["upload"], weight=500)
        ul_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._ul_value_label = self._make_label("0.0 KB/s", 20, _COLORS["upload"], weight=700)
        self._ul_value_label.setMinimumWidth(140)
        self._ul_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        ul_block.addWidget(ul_label)
        ul_block.addWidget(self._ul_value_label)

        layout.addLayout(dl_block, 1)   # stretch factor 1
        layout.addLayout(ul_block, 1)   # stretch factor 1
        return layout

    # ── Section B: Usage History Graph ────────────────────────────────────

    def _build_graph(self):
        graph = pg.PlotWidget()
        graph.setFixedHeight(130)
        graph.setBackground("transparent")

        # Hide all chrome
        graph.hideAxis("left")
        graph.hideAxis("bottom")
        graph.setMouseEnabled(x=False, y=False)
        graph.setMenuEnabled(False)
        graph.hideButtons()
        graph.getPlotItem().getViewBox().setBorder(None)

        x = np.arange(_GRAPH_POINTS)

        # Download area (blue)
        dl_pen = pg.mkPen(color=_COLORS["download"], width=2)
        dl_brush = pg.mkBrush(0, 122, 255, 50)
        self._dl_curve = graph.plot(x, self._dl_history, pen=dl_pen, fillLevel=0, fillBrush=dl_brush)

        # Upload area (red, drawn on top)
        ul_pen = pg.mkPen(color=_COLORS["upload"], width=2)
        ul_brush = pg.mkBrush(255, 59, 48, 40)
        self._ul_curve = graph.plot(x, self._ul_history, pen=ul_pen, fillLevel=0, fillBrush=ul_brush)

        self._graph_widget = graph
        return graph

    # ── Graph Button ──────────────────────────────────────────────────────

    def _build_graph_button(self):
        """Styled button that emits open_graph_requested to open the full GraphWindow."""
        btn = QPushButton("📊  Detailed Graph")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(32)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_COLORS['bg_section']};
                color: {_COLORS['accent']};
                border: 1px solid {_COLORS['separator']};
                border-radius: 6px;
                font-family: {_FONT_FAMILY};
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background: {_COLORS['separator']};
            }}
            QPushButton:pressed {{
                background: {_COLORS['bg']};
            }}
        """)
        btn.clicked.connect(self._on_graph_button_clicked)
        return btn

    def _on_graph_button_clicked(self):
        """Handle graph button click: emit signal and hide dashboard."""
        self.open_graph_requested.emit()
        self.hide_animated()

    # ── Section C: Details Grid ───────────────────────────────────────────

    def _build_details_grid(self):
        outer = QVBoxLayout()
        outer.setSpacing(4)
        outer.addWidget(_SectionTitle("Connection Details"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        # Row 0: Total Download
        grid.addWidget(self._make_label("Total Download", 12, _COLORS["text_secondary"]), 0, 0)
        self._total_dl_label = self._make_label("0 KB", 12, _COLORS["text_primary"], weight=600)
        self._total_dl_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._total_dl_label, 0, 1)

        # Row 1: Total Upload
        grid.addWidget(self._make_label("Total Upload", 12, _COLORS["text_secondary"]), 1, 0)
        self._total_ul_label = self._make_label("0 KB", 12, _COLORS["text_primary"], weight=600)
        self._total_ul_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._total_ul_label, 1, 1)

        # Row 2: Status
        grid.addWidget(self._make_label("Status", 12, _COLORS["text_secondary"]), 2, 0)
        self._status_label = self._make_label("Checking...", 12, _COLORS["text_secondary"], weight=600)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._status_label, 2, 1)

        # Row 3: Latency
        grid.addWidget(self._make_label("Latency", 12, _COLORS["text_secondary"]), 3, 0)
        self._latency_label = self._make_label("— ms", 12, _COLORS["text_primary"], weight=600)
        self._latency_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._latency_label, 3, 1)

        # Row 4: Jitter
        grid.addWidget(self._make_label("Jitter", 12, _COLORS["text_secondary"]), 4, 0)
        self._jitter_label = self._make_label("— ms", 12, _COLORS["text_primary"], weight=600)
        self._jitter_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._jitter_label, 4, 1)

        outer.addLayout(grid)
        return outer

    # ── Section D: Interface & Address ────────────────────────────────────

    def _build_interface_grid(self):
        outer = QVBoxLayout()
        outer.setSpacing(4)
        outer.addWidget(_SectionTitle("Interface"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        grid.addWidget(self._make_label("Interface", 12, _COLORS["text_secondary"]), 0, 0)
        self._iface_name_label = self._make_label("Detecting...", 12, _COLORS["text_primary"], weight=600)
        self._iface_name_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._iface_name_label, 0, 1)

        grid.addWidget(self._make_label("MAC", 12, _COLORS["text_secondary"]), 1, 0)
        self._mac_label = self._make_label("—", 12, _COLORS["text_primary"], weight=600)
        self._mac_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._mac_label, 1, 1)

        grid.addWidget(self._make_label("Local IP", 12, _COLORS["text_secondary"]), 2, 0)
        self._ip_label = self._make_label("—", 12, _COLORS["text_primary"], weight=600)
        self._ip_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self._ip_label, 2, 1)

        outer.addLayout(grid)
        return outer

    # ── Section E: Top Processes ──────────────────────────────────────────

    def _build_processes(self):
        outer = QVBoxLayout()
        outer.setSpacing(4)
        outer.addWidget(_SectionTitle("Active Processes"))

        self._proc_dot_labels = []
        self._proc_name_labels = []
        self._proc_speed_labels = []

        for i in range(5):
            row = QHBoxLayout()
            row.setContentsMargins(0, 2, 0, 2)

            dot = QLabel("●")
            dot.setFixedWidth(16)
            dot.setFixedHeight(18)
            dot.setStyleSheet(
                f"color: {_COLORS['accent']}; "
                f"font-size: 8px; "
                f"padding-top: 2px;"
            )

            proc_name = self._make_label("—", 12, _COLORS["text_tertiary"])
            proc_name.setFixedHeight(18)
            proc_speed = self._make_label("", 12, _COLORS["text_secondary"])
            proc_speed.setFixedHeight(18)
            proc_speed.setAlignment(Qt.AlignmentFlag.AlignRight)

            self._proc_dot_labels.append(dot)
            self._proc_name_labels.append(proc_name)
            self._proc_speed_labels.append(proc_speed)

            row.addWidget(dot)
            row.addWidget(proc_name)
            row.addStretch()
            row.addWidget(proc_speed)
            outer.addLayout(row)

        return outer

    # ── Label factory ─────────────────────────────────────────────────────

    @staticmethod
    def _make_label(
        text: str,
        size: int,
        color: str,
        weight: int = 400,
    ) -> QLabel:
        """Create a styled QLabel with the dashboard font family."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {color}; "
            f"font-family: {_FONT_FAMILY}; "
            f"font-size: {size}px; "
            f"font-weight: {weight}; "
            f"background: transparent; "
            f"padding: 0px 2px; margin: 0px;"
        )
        return lbl


# ─── Standalone test entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    dashboard = AnalyticsDashboard()
    dashboard.show_anchored()
    sys.exit(app.exec())
