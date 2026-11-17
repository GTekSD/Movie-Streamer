<img width="2064" height="512" alt="cover-bg" src="https://github.com/user-attachments/assets/939203ef-e3a6-4379-8f25-3433c126f359" />

# GTekSD Movie Streamer

A lightweight, zero-dependency Python media server that lets you stream local movies and video folders from your Windows PC to Android phones, Android TVs, Smart TVs, iPhones, and iPads over your local Wi-Fi—**without complex SMB permissions, Windows account passwords, or manual filename typing**.

## Features

* **Zero External Dependencies:** Built 100% with Python 3's standard library—no `pip install` required.

* **DLNA / UPnP Auto-Discovery:** Broadcasts itself via SSDP multicast (`239.255.255.250:1900`) so Android, Android TV, and Smart TV players automatically discover and browse your library with zero typing.

* **Fast HTTP Byte-Range Streaming:** Supports `206 Partial Content`, `ETag`, `Last-Modified`, and `If-Range` with 256 KiB chunking for instant scrubbing/seeking in large `.mkv` and `.mp4` files.

* **Read-Only WebDAV Server:** Implements `OPTIONS` and `PROPFIND` (`207 Multi-Status`) so apps like KMPlayer on iOS and Android can browse folders natively without credentials.

* **Dynamic M3U Playlist (`/playlist.m3u`):** Automatically indexes all supported video files (including subfolders) into a single playlist URL for one-tap queueing in VLC and KMPlayer on iOS.

* **Smart LAN IP Detection:** Automatically selects your active Wi-Fi/Ethernet IPv4 address while ignoring loopback (`127.x`), link-local (`169.254.x`), and VirtualBox Host-Only (`192.168.56.x`) adapters.

* **Rotating Debug Logging:** Writes thread-safe debug logs to `movie_server.log` (5 MiB rotation, 3 backups), silences missing subtitle-probe (`404`) spam in the console, and cleanly handles player socket disconnects.

## Requirements

* **Python 3.8+** (tested on Python 3.13 on Windows 11)

* Server PC and client devices connected to the **same local Wi-Fi / LAN** (with no VPN or router guest-isolation blocking local traffic)

## Quick Start

1. Place `movie_server.py` inside the folder containing your movies (or pass any folder path as an argument).

2. Open PowerShell or Command Prompt and run:

```
# Share the current directory on default port 8000
python .\movie_server.py

# Share a specific folder
python .\movie_server.py "C:\Users\suhas\Videos\MOVIE"

# Share on a custom port
python .\movie_server.py "C:\Users\suhas\Videos\MOVIE" -p 9000

```

3. Keep the terminal window open while watching. Press `CTRL + C` to stop the server cleanly.

### CLI Options

| Flag / Argument | Default | Description | 
| ----- | ----- | ----- | 
| `folder` | `.` (current folder) | Directory to expose on your local network. | 
| `-p`, `--port` | `8000` | TCP port for HTTP, WebDAV, M3U, and DLNA control. | 
| `--log-file <path>` | `./movie_server.log` | Custom path for the rotating debug log file. | 
| `--debug` | `False` | Also print verbose `DEBUG` logs live in the terminal. | 
| `--no-log` | `False` | Disable writing logs to disk. | 

## One-Time Windows Firewall Setup

If your phone or TV cannot see or connect to the server, Windows Defender Firewall is likely blocking incoming traffic on your Wi-Fi network (or your Wi-Fi profile is set to **Public** instead of **Private**).

Open **PowerShell as Administrator** on your PC and run these three commands once:

```
# 1. Set your active network connection profile to Private
Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private

# 2. Allow inbound TCP port 8000 (HTTP streaming, WebDAV, and M3U playlists)
New-NetFirewallRule -DisplayName "GTekSD Movie Streamer (HTTP)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private

# 3. Allow inbound UDP port 1900 (DLNA / UPnP auto-discovery)
New-NetFirewallRule -DisplayName "GTekSD Movie Streamer (DLNA)" -Direction Inbound -Protocol UDP -LocalPort 1900 -Action Allow -Profile Private

```

*(If you run the server on a custom port with `-p`, update `-LocalPort` in rule #2 accordingly.)*

## How to Connect from Your Devices

Replace `<PC_IP>` and `<PORT>` with the values printed in the startup banner (for example, `192.168.1.11` and `8000`).

### Android & Android TV (UPnP — Zero Typing, No Password)

Recommended apps: **NOVA Video Player**, **VLC for Android**, or **KMPlayer**.

* **NOVA Video Player:**
  `Network & Files` → `Network` → `Media server (UPnP)` → **`GTekSD Movie Streamer (<Hostname>)`**

* **VLC for Android:**
  `Browse` → `Local Network` → **`GTekSD Movie Streamer (<Hostname>)`**

* **KMPlayer:**
  `Network` → `Auto-discovered UPnP` → **`GTekSD Movie Streamer (<Hostname>)`**

### iOS (iPhone / iPad)

* **KMPlayer (Folder Browsing via WebDAV):**

  1. Open `Network` → tap **`Add (+)`** → choose **`WEBDAV`**

  2. **Host / IP:** `<PC_IP>` *(enter the IP only — do not include `http://` or `:8000`)*

  3. **Port:** `8000`

  4. **User ID / Password:** Leave blank and save.

* **KMPlayer (Playlist / Direct URL):**
  Open `Network` → `URL Playback` → enter `http://<PC_IP>:8000/playlist.m3u` (or `http://<PC_IP>:8000/movie.mkv`).

* **VLC for iOS:**
  Open `Browse` → `Open Network Stream` → enter `http://<PC_IP>:8000/playlist.m3u` to load all videos into VLC's playlist queue, or paste a direct file URL.

### Web Browser (Any Device)

* **Folder Directory:** `http://<PC_IP>:8000/`

* **M3U Playlist:** `http://<PC_IP>:8000/playlist.m3u`

## Supported Media Formats

The DLNA catalog and `/playlist.m3u` generator automatically index the following file extensions (case-insensitive):

`.mkv`, `.mp4`, `.avi`, `.mov`, `.m4v`, `.webm`, `.ts`, `.m2ts`, `.wmv`, `.flv`, `.mpg`, `.mpeg`

*(Direct HTTP downloads and WebDAV browsing serve all files in the shared folder, including external subtitle files like `.srt`, `.ass`, and `.vtt`.)*

## Logging & Debugging

Every run automatically writes detailed `DEBUG` logs to `movie_server.log` (up to **5 MiB** per file with **3** rotated backups).

To watch live debug logs in a second PowerShell window:

```
Get-Content .\movie_server.log -Wait -Tail 30

```

Or print verbose debug output directly in the main server console:

```
python .\movie_server.py --debug

```

## Troubleshooting

| Symptom | Cause & Fix | 
| ----- | ----- | 
| Nothing appears in `movie_server.log` when connecting from phone/TV | Traffic is blocked before reaching Python. Run the **Windows Firewall** commands above, verify both devices are on the same Wi-Fi band/subnet, and disable any active VPN. | 
| Server prints a `192.168.56.x` VirtualBox IP | `v1.6` automatically filters out `192.168.56.*`. If you use another virtual adapter (VMware/WSL), check `ipconfig` for your Wi-Fi adapter's IPv4 address. | 
| `Could not start server on port 8000` | Another app is already using port `8000`. Run with `-p 8080` (or any free port). | 
| Server not showing in UPnP list on Android/TV | Ensure UDP port `1900` is allowed in Windows Firewall and that your Wi-Fi router does not block multicast / IGMP traffic. | 

## Security Notice

This server is designed for trusted **home local networks (LAN)** and intentionally requires no authentication. Only share folders you are comfortable exposing to devices connected to your Wi-Fi, and close the terminal window when finished.

## License

Copyright (C) 2026 **GTekSD**. All rights reserved.
