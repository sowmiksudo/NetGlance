# NetGlance v2.0.0-beta

We are thrilled to announce **NetGlance v2.0.0-beta**! This major update brings dynamic UI improvements, expanded resource monitoring, and vital inner-workings to push NetGlance closer to a stable 2.0 release.

### ✨ What's New

- **Analytics Dashboard Anchoring**: The dashboard now elegantly tracks your taskbar widget. Whether your taskbar is on the left, right, top, or bottom, the analytical window automatically anchors and centers itself around the widget, adapting dynamically to screen bounds to ensure nothing is cut off.
- **System Resource Monitoring**: Keep an even closer eye on your PC's health! We've integrated comprehensive CPU and RAM usage statistics right alongside your network speed directly within the taskbar widget.
- **About Page & Auto-Updater Check**: We've introduced a dedicated **About** tab in your Settings dialog. Need a quick link to the repository? It’s there! Wondering if you’re on the latest build? Just hit "Check for Updates" and the application will tap into the official GitHub API to let you know if a newer version is ready to install.

### 🛠️ Fixes & Adjustments

- Fixed an issue where the `VersionInfoVersion` directive would cause Inno Setup compilation to fail during the build process.
- Ensured seamless `I18n` language failovers by explicitly handling translation edge-cases within Settings dialog properties.

---

### 📦 Installation

To install or upgrade:
1. Download `NetGlance-2.0.0-beta-x64-Setup.exe` below.
2. Run the installer and follow the instructions.
3. If you prefer a non-installed version, grab `NetGlance-Portable-2.0.0-beta.zip` and extract it to a directory of your choice.

### ✅ Checksums (SHA-256)
Please verify your downloads using the checksums provided in the `checksums.txt` file within the release assets.

**Thank you for testing the NetGlance v2.0.0-beta release!** Please feel free to open an issue if you catch any bugs or have feature suggestions.
