# ISWM Plant App

A Windows desktop app for the ISWM Donthali weighbridge. It's built from the Claude Design prototype. The hardware code is adapted from [tsaaii/adex_lite](https://github.com/tsaaii/adex_lite).

- **Screens:** 1 Inward · 2 Outward · 3 Material recovery · 4 Tare · 5 Sync · 6 Reports, plus PIN sign-in. Admin settings are hidden from operators.
- **Weighbridge:** serial (COM port) or `socket://ip:port`, with the weight read by a regex and multiplier as in adex_lite. A built-in simulator is available for training.
- **Cameras:** front and back, each USB, RTSP (Hikvision / Dahua / CP Plus / other) or HTTP. Live preview with zoom. Save stores full-resolution, watermarked photos.
- **Records:** SQLite. Tickets are `IN{R|C}YYMM####` and `O YYMM####`, from counters that never reset.
- **Sync:** to Google Cloud Storage in the background. Works offline.
- **Reports:** Daily, Shift, Incomplete, and Hourly/Daily/Weekly/Monthly with CSV download.

## Install (for anyone)

1. Open the repository on GitHub → **Actions** → the latest green **Build Windows installer** run → download **ISWM-Setup** under *Artifacts*. For a tagged version, use **Releases** instead.
2. Unzip it and double-click **ISWM-Setup.exe**. If Windows says "Windows protected your PC", click **More info → Run anyway**. The installer is not code-signed yet.
3. Click **Next** until it finishes. It puts an **ISWM Plant** icon on the desktop and in the Start menu, and installs Microsoft Edge WebView2 if the PC doesn't have it.
4. The app opens on **Set up the plant**. Type the site name, make an **admin password**, and add the first operator with a 4-number PIN. Write the admin password down.

Data (records, photos, settings, logo) is kept in `C:\ProgramData\ISWM`. Back up that folder. Uninstalling the app does not delete it, and installing a newer `ISWM-Setup.exe` over the old one keeps everything.

There's also **ISWM-portable** (a zip). Unzip it anywhere and run `ISWM.exe`. Its data goes in `ISWM_data` next to the exe.

## Admin (hidden from operators)

Operators never see admin controls. To open them, press **Ctrl + Shift + A**, or tap the **site name 5 times** (top-left, or the big name on the sign-in screen), then type the admin password. An **Admin** button and a **Lock** button then appear in the top bar. Admin locks itself after 15 minutes without use, and five wrong passwords block tries for a minute.

Only the admin can change:
- site name, company and **logo** (PNG/JPG/WebP, under 2 MB, shown on the sign-in screen and top bar);
- operators and their PINs (each operator needs their own PIN; easy PINs like 1111 or 1234 are refused);
- the admin password (8+ characters, letters and numbers, must not contain an operator's PIN);
- weighbridge, cameras, Google Cloud sync, ticket serials and the reports folder.

There are no default passwords or PINs.

## Keyboard only, or mouse only

Everything works with just a keyboard or just a mouse. Press **F1** in the app to see the keys.

| | Keyboard | Mouse only |
|---|---|---|
| Sign in | ← → pick your name (the last person is already picked); type the PIN on the number row or number pad. Backspace undoes, Delete clears. | Tap your name, tap the PIN keys |
| Change screen | Alt + 1 … 6 | Tap the tabs |
| Vehicle | Just start typing. ↑ ↓ choose, Enter picks | Tap the box and pick from the list, or tap **Type on screen** for a new number |
| Save | Enter again in the vehicle box once the weight is steady, or Ctrl + S | Tap Save |
| Inward From / Waste | Alt + R / C, Alt + M / W / D | Tap |
| Outward | Enter moves Vehicle → Material → Going to; type a material's first letter; Alt + K small scale | Tap |
| Other boxes and buttons | Tab / Shift + Tab, Enter or Space | Tapping a typing box opens an on-screen keyboard (a number pad for weights) |
| Close | Esc | × or Cancel |
| Admin | Ctrl + Shift + A | Tap the site name 5 times |

## Cameras: getting the clearest picture

Pick **Type → RTSP** and the camera **Brand**. The brand fills in the best endpoints, so you only type the IP, user name and password. Passwords with `@ : / #` work, because they're encoded properly in the address.

| Brand | Stream endpoint (main stream) | Photo snapshot endpoint |
|---|---|---|
| Hikvision | `/Streaming/Channels/101` | `/ISAPI/Streaming/channels/101/picture` |
| Dahua, CP Plus | `/cam/realmonitor?channel=1&subtype=0` | `/cgi-bin/snapshot.cgi?channel=1` |
| Other | from the camera's manual (often `/stream1`) | leave empty |

Why photos are sharper than adex_lite's:
- **Main stream, not sub-stream.** Hikvision `101` / Dahua `subtype=0` is the camera's full resolution. `102` / `subtype=1` is the small preview stream.
- **No forced 640×480.** adex_lite asked every camera for 640×480. This app keeps the camera's own resolution. Admin shows it, for example "Live at 1920 × 1080", and warns when it's below 1280.
- **RTSP over TCP.** Over UDP, lost packets smear and grey-out parts of the picture. TCP avoids that.
- **Saved photos use the camera's own JPEG snapshot** when a snapshot endpoint is set. That picture has no video-compression blur. If the snapshot fails, the app falls back to the full-size video frame. Photos are saved at JPEG quality 95. Only the on-screen preview is made smaller.
- **USB cameras** are asked for 1920×1080 MJPG instead of 640×480.

On the camera itself (in its web page), these settings help most for number plates and loads:
- Main stream at the highest resolution, **H.264** (H.265 can be slower to decode), at 15–25 fps.
- Bitrate type **Constant**, about 4096–6144 kbps for 1080p and 8192 kbps for 4 MP.
- I-frame interval equal to the frame rate (for example 25), so the picture recovers quickly after a truck moves.
- **WDR** on for gates facing bright sky, and a fast shutter (1/250 s or faster) so moving plates don't blur.
- A fixed IP address for each camera, so the app always finds it.

## Rules the app enforces

- Each vehicle gets one empty (tare) weight for its whole life. An inward trip from a vehicle with no tare is saved with its gross and stays *incomplete* until the vehicle is weighed empty on screen 4.
- Outward needs a vehicle that already has a tare, or a small-scale manual weight with a reason; manual entries are marked.
- Save takes the weight and both photos together. It works only when the weight is steady (within the set kg for the set seconds) and above the minimum (default 10 kg). This guards against misclicks.
- Net weight counts in reports only for complete records, meaning ones with both gross and tare.
- Saved entries are never edited in the app. Operators use **Ask to correct (52)**, and the request is uploaded for the admin.

## Build it yourself

GitHub builds the installer on every push (`.github/workflows/build-exe.yml`). To build on a Windows PC instead, double-click `build.bat`. It makes a `.venv`, installs everything and builds `dist\ISWM\ISWM.exe`. By hand, in Command Prompt:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm ISWM.spec
```

For the installer as well, install [Inno Setup 6](https://jrsoftware.org/isdl.php), download the [WebView2 bootstrapper](https://go.microsoft.com/fwlink/p/?LinkId=2124703) to `installer\MicrosoftEdgeWebview2Setup.exe`, then run `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ISWM.iss`. The result is `dist\ISWM-Setup.exe`.

## Run from source

```bash
python -m venv .venv && .venv\Scripts\activate     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python run_iswm.py              # app window
python run_iswm.py --browser    # no window: prints a URL to open in a browser
python -m pytest -q tests
```

## Layout

| Path | What |
|---|---|
| `iswm/db.py` | SQLite schema, tickets, tare/complete rules, recovery batches, sync queue, reports |
| `iswm/weighbridge.py` | Serial reader (adapted from adex_lite), stability check, simulator |
| `iswm/cameras.py` | OpenCV capture threads, watermark (from adex_lite), snapshot |
| `iswm/cloud.py` | Google Cloud Storage uploader (bucket layout from adex_lite) |
| `iswm/service.py` | One method per UI action |
| `iswm/server.py` | Local HTTP server on 127.0.0.1 with a per-launch token, camera MJPEG streams |
| `iswm/main.py` | Starts everything and opens the pywebview window |
| `installer/ISWM.iss` | Inno Setup script for `ISWM-Setup.exe` |
| `web/` | The screens: React + htm, using the Tharuni design-system bundle, offline |
| `project/`, `chats/`, `HANDOFF.md` | The original Claude Design handoff |

## Not in the prototype, added here

- First-run **Set up the plant** screen. Hidden admin settings, with a lock.
- Logo upload.
- **End shift** under the operator's name.
- A red **Not saved** line when the app refuses a save.
- Sync shows **Sync off** until it is set up.
- Download writes two CSVs, the summary and every trip, and offers **Open folder**.
