<img width="2064" height="512" alt="cover-bg" src="https://github.com/user-attachments/assets/afb8c80d-6d3f-4621-a19e-f10e9912fb4c" />
# GTekSD Movie Streamer

![Version](https://img.shields.io/badge/version-1.7-58a6ff?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Python%203-238636?style=flat-square)
![Dependencies](https://img.shields.io/badge/dependencies-Zero%20(Stdlib%20Only)-8b949e?style=flat-square)

**GTekSD Movie Streamer** is a lightweight, zero-dependency local media server with a compact dark-mode desktop GUI. Stream your local movie and video folders effortlessly across your home Wi-Fi or LAN to Smart TVs, Android devices, iPhones/iPads, and web browsers using **HTTP**, **WebDAV**, and **DLNA / UPnP**.

---

## Features

* **Multi-Protocol Streaming Engine:**
  * **DLNA / UPnP Auto-Discovery (SSDP):** Automatically advertises your shared folder on your local network so Smart TVs and mobile players detect it with zero manual IP entry.
  * **HTTP/1.1 Byte-Range Streaming:** Supports `206 Partial Content` and `ETag` caching for smooth playback and instant seeking/scrubbing on large video files.
  * **WebDAV Support (`PROPFIND` / `OPTIONS`):** Browse folders natively from iOS and mobile media apps.
  * **Auto-Generated M3U Playlist (`/playlist.m3u`):** Dynamically builds a playable network stream playlist of all videos in your selected folder and subfolders.
* **Compact Dark-Mode GUI & Native System Tray:**
  * Clean dark interface with Windows dark title bar and High-DPI scaling support.
  * Native 64-bit-safe Windows system tray integration with **Close to Tray**, balloon notifications, and quick-access controls (Start/Stop, Open in Browser, Copy Stream URL).
  * Built-in **Client Guide** tabs with ready-to-use URLs and instructions for Android, TV, iOS, and browsers.
* **Zero External Runtime Dependencies:** Built entirely on the Python 3 standard library—and available as a single standalone `GTekSD Movie Streamer.exe`.

### Supported Video Formats
`.mkv` • `.mp4` • `.avi` • `.mov` • `.m4v` • `.webm` • `.ts` • `.m2ts` • `.wmv` • `.flv` • `.mpg` • `.mpeg`

---

## Quick Start

### Option 1: Standalone Windows Executable (Recommended)
1. Go to the **[Releases](../../releases)** page and download **`GTekSD Movie Streamer.exe`**.
2. Double-click **`GTekSD Movie Streamer.exe`** to launch the app (no Python installation required).
3. When prompted by **Windows Defender Firewall**, check **Private networks** and click **Allow access**.
4. Click **Browse** to select your video folder, verify your **LAN IP** and **Port** (default `8000`), and click **▶ Start**.

### Option 2: Run from Python Source
Requires **Python 3.8+** (no `pip install` packages required):
```bash
git clone https://github.com/GTekSD/Movie-Streamer.git
cd Movie-Streamer
python movie_server.py
```

---

## Connecting Your Devices

Make sure your phone, tablet, or TV is connected to the **same Wi-Fi / LAN** as your PC, and ensure your PC's Wi-Fi profile in Windows is set to **Private** (not Public).

### Android / Smart TV (DLNA / UPnP)
Your server appears automatically as **`GTekSD Movie Streamer (<PC-Name>)`**:
* **VLC for Android / TV:** `Browse` → `Local Network` → select **`GTekSD Movie Streamer`**
* **KMPlayer:** `Network` → auto-discovered **UPnP** device → **`GTekSD Movie Streamer`**
* **NOVA Video Player:** `Network & Files` → `Network` → `Media server (UPnP)` → **`GTekSD Movie Streamer`**

### iPhone / iPad (WebDAV or Network Stream)
* **KMPlayer (WebDAV):** `Network` → `Add (+)` → `WEBDAV` → enter your PC's **LAN IP** and **Port** (`8000`)
* **KMPlayer (M3U Stream):** `URL Playback` → `http://<PC_IP>:8000/playlist.m3u`
* **VLC for iOS:** `Network` → `Open Network Stream` → `http://<PC_IP>:8000/playlist.m3u`

### Web Browser / Direct Links
* **Folder Browser:** `http://<PC_IP>:8000/`
* **Full M3U Playlist:** `http://<PC_IP>:8000/playlist.m3u`
* **Direct Video File:** `http://<PC_IP>:8000/<filename.mkv>`

---

## Command-Line Options

You can launch either `GTekSD Movie Streamer.exe` or `python app.py` with optional CLI flags (useful for Windows Startup shortcuts):

| Argument | Description |
| :--- | :--- |
| `[folder]` | Optional path to the media folder to share on launch |
| `-p`, `--port <number>` | Set the HTTP/WebDAV port (default: `8000`) |
| `--autostart` | Automatically start streaming as soon as the app launches |
| `--minimized` | Launch minimized directly into the Windows system tray |
| `--debug` | Enable verbose debug logging in the GUI and log file |
| `--no-log` | Disable writing the rotating `movie_server.log` file to disk |

**Example (Silent Auto-Start in System Tray):**
```bash
"GTekSD-Movie-Streamer.exe" "D:\Movies" -p 8000 --autostart --minimized
```

---

## Configuration & Logs

* **Saved Settings:** Automatically stored in `~/.gteksd_movie_streamer.json` (remembers your last shared folder, port, logging toggles, and tray preference).
* **Activity Logs:** When **Save Log** is enabled, rotating logs (up to 5 MB × 3 backups) are saved to `movie_server.log` in the application directory.

---

## License

Copyright (C) 2026 **GTekSD**. All rights reserved.
