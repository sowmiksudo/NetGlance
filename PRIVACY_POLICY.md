# Privacy Policy for NetGlance

**Last Updated:** April 9, 2026  
**Application Version:** 2.0.0  
**Developer:** Shayer Mahmud Sowmik

---

## Overview

NetGlance is an open-source network monitoring utility for Windows. This privacy policy describes what information the application accesses, how it is used, and how it is stored.

**NetGlance does not collect, transmit, or share any personal data with the developer or any third party.** All data stays on your device.

---

## Information Accessed

NetGlance accesses the following system information solely to provide its core functionality:

### Network Statistics
- **Upload and download speed** — polled from Windows network counters via the `psutil` library to display real-time bandwidth usage.
- **Total data transferred** — cumulative byte counts for your current session.
- **Network interface names** — (e.g., "Wi-Fi", "Ethernet") used to identify which adapter is being monitored.

### Network Configuration (displayed in the Analytics Dashboard)
- **Local IP address** — your device's local/private IP address on your network (not your public IP).
- **MAC address (Physical Address)** — your network adapter's hardware identifier.
- **Active network interface** — the name of the adapter currently connected to the internet.

### Connection Quality
- **Latency (ping)** — measured by sending ICMP echo requests to Google's public DNS server (8.8.8.8) every 2 seconds.
- **Jitter** — calculated from the variance of recent latency measurements.
- **Connection status** — whether your device can reach the internet.

### Active Network Processes
- **Process names** — the names of applications with active network connections (e.g., "chrome.exe", "Spotify.exe"). Only the process name is accessed; no process content, communications, or user data within those applications is read.

### System Resources
- **CPU usage percentage** — overall system CPU load.
- **RAM usage percentage** — overall system memory usage.

---

## Information Stored Locally

NetGlance stores the following data on your device in the `%APPDATA%\NetGlance\` directory:

| Data | File | Retention |
|---|---|---|
| Network speed history | `netglance.db` (SQLite) | Configurable: 7 days to 1 year (default: 1 year) |
| Application settings | `NetSpeedTray_Config.json` | Until manually reset or app is uninstalled |
| Application logs | `netspeedtray.log` | Rolling log, max 1 MB with 3 backups |

### Log File Privacy
Application log files automatically **redact sensitive information** before writing. User file paths and IP addresses are replaced with `<REDACTED_PATH>` and `<REDACTED_IP>` to protect your privacy even if log files are shared for troubleshooting.

### Data Deletion
- You can delete all stored data by uninstalling NetGlance and selecting **"Yes"** when prompted to delete user settings, history, and log files.
- You can manually delete the `%APPDATA%\NetGlance\` directory at any time.
- You can change the data retention period in **Settings → General → Data Retention**.

---

## External Network Connections

NetGlance makes the following outbound network connections:

| Destination | Protocol | Purpose | Frequency |
|---|---|---|---|
| `8.8.8.8` (Google DNS) | ICMP (ping) | Measure network latency and jitter | Every 2 seconds |
| `8.8.8.8:80` (Google DNS) | UDP (no data sent) | Determine which network interface is the default route | Once at startup |
| `api.github.com` | HTTPS | Check for application updates | Only when you click "Check for Updates" |

**No personal information is transmitted** in any of these connections. The ICMP ping and UDP socket send only standard protocol headers. The GitHub API request sends only a `User-Agent: NetSpeedTray` header and receives public release information.

---

## Third-Party Services

NetGlance does **not** use any analytics services, advertising networks, crash reporting services, or telemetry systems. The only third-party connection is to the GitHub API for optional update checking, which is user-initiated.

---

## Data Sharing

NetGlance does **not** share, sell, transmit, or otherwise distribute any user data to:
- The developer
- Any third party
- Any server or cloud service
- Any advertising or analytics platform

All data processing occurs entirely on your local device.

---

## Children's Privacy

NetGlance does not knowingly collect any personal information from children under the age of 13. The application does not require account creation, does not communicate with other users, and does not display advertising.

---

## Windows Registry

NetGlance may write a single entry to the Windows Registry if you enable the "Start with Windows" setting:
- **Key:** `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- **Value:** Path to the NetGlance executable

This entry is removed when you disable the setting or uninstall the application.

---

## Open Source

NetGlance is open-source software licensed under the GNU General Public License v3.0. You can review the complete source code at:

**https://github.com/sowmiksudo/NetGlance**

---

## Changes to This Policy

This privacy policy may be updated when new features are added to the application. Changes will be reflected in the "Last Updated" date at the top of this document and in the application's changelog.

---

## Contact

If you have questions about this privacy policy, you can:
- Open an issue on GitHub: https://github.com/sowmiksudo/NetGlance/issues
- Contact the developer: Shayer Mahmud Sowmik

---

*This privacy policy applies to NetGlance version 2.0.0-beta and later.*
