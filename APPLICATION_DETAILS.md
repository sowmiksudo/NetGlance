# Extension Plan: NetSpeedTray -> macOS-Style Analytics Dashboard
**Base Repository:** `https://github.com/erez-c137/NetSpeedTray`
**Objective:** Replace the default secondary windows with a unified, frameless, modern analytics panel inspired by macOS menu-bar tools.


## 1. Architectural Changes to Base Repo
The base repo currently separates the "Settings Dialog" and the "Detailed History Graph". We will combine and replace these with a single `AnalyticsDashboard` widget.

* **Hooking the Event:** In the base repo's main widget class (likely inside `src/monitor.py` or the UI folder), locate the `mouseDoubleClickEvent` or system tray click events. Redirect these to instantiate/show the new `AnalyticsDashboard` class instead of the default graph.
* **Data Sharing:** The base repo already has a highly optimized data-fetching loop (using NumPy vectorization). The new `AnalyticsDashboard` must connect to the existing data signals emitted by the core worker thread so both the taskbar widget and the new dashboard stay perfectly synced.

## 2. The New Module: `analytics_dashboard.py`
This will be a new file added to the `src/` directory. It will subclass a frameless `QWidget` (using PyQt/PySide) and use a vertical layout (`QVBoxLayout`) to stack the analytics sections.

### Section A: Top Header (Total Speeds)
* **UI Elements:** Two large `QLabel`s for current Upload (Red) and Download (Blue) speeds in KB/s.
* **Logic:** Fed directly by the existing `NetSpeedTray` data emitter.

### Section B: Usage History Graph
* **UI Elements:** A `pyqtgraph.PlotWidget`. 
* **Styling:** Hide axes and grids. Create two `PlotDataItem`s using `fillLevel`. Set the Download fill to blue (`#007AFF`) and Upload fill to red (`#FF3B30`).
* **Logic:** Feed the last ~60 seconds of the NumPy arrays already maintained by the base repo into this graph.

### Section C: Details Grid
* **UI Elements:** A `QGridLayout` displaying static and semi-static text.
* **Data Sources:**
    * **Total Upload/Download:** Fetch using `psutil.net_io_counters().bytes_sent` / `bytes_recv` (converted to GB).
    * **Status & Internet Connection:** Simple HTTP request to `1.1.1.1` or checking `psutil.net_if_stats()`.
    * **Latency & Jitter:** Run a separate lightweight `QThread` using the pure-Python `ping3` library to ping `8.8.8.8` every 2 seconds. Keep a small array of the last 5 pings to calculate Jitter (variance).

### Section D: Interface & Address
* **UI Elements:** `QGridLayout`.
* **Data Sources:**
    * **Interface:** Use `psutil.net_if_addrs()` to find the active interface (e.g., Wi-Fi or Ethernet).
    * **Physical Address (MAC):** Extract from `psutil.net_if_addrs()` where `family == psutil.AF_LINK`.
    * **Local IP:** Extract from `psutil.net_if_addrs()` where `family == socket.AF_INET`.

### Section E: Top Processes (The Hard Part)
* **UI Elements:** A `QTableWidget` or vertical list of `QLabel`s with application icons.
* **Technical Limitation Warning for AI:** Pure Python on Windows *cannot* natively fetch real-time byte counts per process without Event Tracing for Windows (ETW) or running packet sniffers as Administrator. 
* **Workaround:** For MVP, use `psutil.net_connections()` to list processes that currently have *active network sockets* (ESTABLISHED status). Display the process name (e.g., `chrome.exe`, `Spotify.exe`) and placeholder `0 KB/s` until a C++ extension or ETW integration is built in a future phase.

## 3. Theming and UI Execution
* **Frameless Window:** The `AnalyticsDashboard` must use `Qt.WindowType.FramelessWindowHint` and a custom CSS stylesheet to mimic the rounded corners, white/dark background, and specific fonts seen in the reference image.
* **Positioning Logic:** When triggered, the AI must calculate the screen coordinates of the `NetSpeedTray` taskbar widget and spawn the `AnalyticsDashboard` directly above it (offsetting by the height of the dashboard).
* **Focus Loss:** Implement `focusOutEvent` so that if the user clicks anywhere else on their Windows desktop, the `AnalyticsDashboard` gracefully hides itself (`self.hide()`).