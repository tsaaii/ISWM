# ISWM Plant App

A Windows desktop app for the ISWM Donthali weighbridge. It's built from the Claude Design prototype. The hardware code is adapted from [tsaaii/adex_lite](https://github.com/tsaaii/adex_lite).

- **Screens:** 1 Inward · 2 Outward · 3 Material recovery · 4 Tare · 5 Sync · 6 Reports, plus PIN sign-in. Admin settings are hidden from operators.
- **Weighbridge:** serial (COM port) or `socket://ip:port`, with the weight read by a regex and multiplier as in adex_lite. A built-in simulator is available for training.
- **Cameras:** front and back, plus up to 6 more (8 in all), each USB, RTSP (Hikvision / Dahua / CP Plus / other) or HTTP. Live preview with zoom from 0.75× (whole picture) to 4×. Save stores full-resolution, watermarked photos.
- **Records:** SQLite. Tickets are `IN{R|C}YYMM####` and `O YYMM####`, from counters that never reset.
- **Sync:** records to Google Cloud **Firestore**, batched to use very little internet. Works offline. A shared real-time API is in `cloud_api/`.
- **Reports:** Daily, Shift, Incomplete, and Hourly/Daily/Weekly/Monthly with CSV download.

## Install (for anyone)

1. Open the repository on GitHub → **Actions** → the latest green **Build Windows installer** run → download **ISWM-Setup** under *Artifacts*. For a tagged version, use **Releases** instead.
2. Unzip it and double-click **ISWM-Setup.exe**. If Windows says "Windows protected your PC", click **More info → Run anyway**. The installer is not code-signed yet.
3. Click **Next** until it finishes. It puts an **ISWM Plant** icon on the desktop and in the Start menu.
4. The app opens on **Set up the plant**. Type the site name, make an **admin password**, and add the first operator with a 4-number PIN. Write the admin password down.

Data (records, photos, settings, logo) is kept in `C:\ProgramData\ISWM`. Back up that folder. Uninstalling the app does not delete it, and installing a newer `ISWM-Setup.exe` over the old one keeps everything.

There's also **ISWM-portable** (a zip). Unzip it anywhere and run `ISWM.exe`. Its data goes in `ISWM_data` next to the exe.

## Very low data use

| | What happens | Data |
|---|---|---|
| Cameras | **Off** until needed. They run only while an operator presses **View live** (Alt + V), while the admin preview or a live-view viewer is watching, or briefly after a vehicle is picked so the photo is ready. With a *snapshot endpoint* set, Save asks the camera for one picture and no video stream is opened at all. They stop about 20 seconds after the need ends. | Local network only, never internet |
| Sync | New records are collected and sent together every 10 minutes (admin can choose right away, or 5 / 15 / 30 / 60 minutes), in one request. **Nothing is sent when nothing is new.** No polling, no keep-alive. When offline, the wait doubles, up to an hour. | About 1 KB per trip |
| Photos | Stay on the PC by default. Admin can choose *Small* (about 100 KB) or *Full* (about 0.5 MB) upload to a Cloud Storage bucket. | 0 by default |
| Screens, reports, live view | Run on the PC and the local network | none |

The Sync screen shows when records were last sent, when the next send is, and how much internet the app has used since it started.

## Google Cloud: database and shared API

**Why Firestore.** [Firestore](https://cloud.google.com/firestore) has no server to keep running, so it costs nothing while idle. Its free daily quota (20,000 writes, 50,000 reads, 1 GB stored) covers several plants of a few hundred trips each, and it has real-time updates built in. Cloud SQL would cost about $10–30 a month even when idle.

**Layout.** One project, one tree per site:
```
sites/{site_id}                     name, company, last_sync
sites/{site_id}/entries/{ticket}    each trip: vno, dir, source/waste_type or material/dest,
                                    gross_kg, tare_kg, net_kg, manual, operator, created_at, ...
sites/{site_id}/tares/{id}          sites/{site_id}/vehicles/{vehicle}
sites/{site_id}/batches|samples|corrections/{id}
```
Each site keeps its own local database (SQLite) as the source of truth, so the plant works with no internet. To give a site a completely separate Firestore database, create a named database and type its name in *Firestore database*.

**Set up (once, in the Google Cloud console).**
1. Firestore → *Create database* → Native mode → region `asia-south1` (Mumbai).
2. IAM → Service accounts → create `iswm-plant` with the role **Cloud Datastore User**. Keys → Add key → JSON. Copy the file to the plant PC, for example `C:\ISWM\key.json`.
3. In ISWM admin, under *Sync to Google Cloud*: tick **Turn on sync**, give the key file path and a **Site ID** that is different for every site (for example `iswm-donthali`), then **Save settings**. The project is read from the key file.
4. Only for photo upload: create a Cloud Storage bucket, give the service account **Storage Object Creator** on it, and type the bucket name.

**Shared real-time API (`cloud_api/`).** A small read-only service for [Cloud Run](https://cloud.google.com/run). It scales to zero, so it's free while nobody calls it, and Cloud Run's free tier covers 2 million requests a month.

```bash
cd cloud_api
gcloud run deploy iswm-api --source . --region asia-south1 --allow-unauthenticated \
  --set-env-vars "API_KEYS=office:LONG-RANDOM-KEY-1,dashboard:LONG-RANDOM-KEY-2@iswm-donthali"
```
Give the Cloud Run service account the **Cloud Datastore Viewer** role. Then share a key with each consumer:

| Call | Gives |
|---|---|
| `GET /v1/sites` | the sites this key can see |
| `GET /v1/sites/iswm-donthali/entries?from=2026-10-01&to=2026-10-11&vehicle=AP39` | trips with vehicle numbers |
| `GET /v1/sites/iswm-donthali/summary?date=2026-10-11` | trips and net kg by waste type or material |
| `GET /v1/sites/iswm-donthali/vehicles` | vehicles and their empty weights |
| `GET /v1/sites/iswm-donthali/stream` | **live**: an event for each new or changed trip as it arrives (Server-Sent Events) |

Every call needs the header `X-API-Key: <key>`. A key written as `name:key@site1|site2` only sees those sites. `firestore.rules` blocks all direct access, so data is reachable only through the API.

"Real time" means as soon as the plant sends. With the default 10-minute batching, the API is at most about 10 minutes behind. Choose *Right away* in admin for seconds, at the cost of one small request per trip.

## Where data is kept

Everything is in one folder. Installed: `C:\ProgramData\ISWM`. Portable: `ISWM_data` next to `ISWM.exe`.

| Inside | What | Kept for |
|---|---|---|
| `iswm.sqlite3` | every trip, tare, batch, sample, correction and admin fix | forever |
| `settings.json` (+ `.bak`, and a copy inside the database) | settings | — |
| `images\YYYY-MM-DD\` | 2 photos per trip, about 0.3–0.8 MB each at 1080p | 90 days (admin can change; 0 = forever) |
| `reports\` | downloaded CSV files | 180 days |
| `backups\` | one copy of the database per day | 30 days |
| `logs\` | one log per day | 60 days |
| `branding\` | the logo | — |

At about 200 trips a day, photos use roughly 0.1–0.3 GB a day, so 90 days is roughly 10–30 GB. Admin → *Storage and clean-up* shows the real sizes and free disk. Photos are never removed while their trip is still waiting to upload. Back up the whole folder, or turn on Google Cloud sync.

**Power cuts, firewalls and antivirus.** adex_lite rewrote `app_settings.json` in place. A cut, or another program holding the file, could leave it empty, and an unreadable file was then replaced with defaults. This app instead:
- saves to a temporary file, forces it to disk, then swaps it in with one atomic rename, retrying for up to 5 seconds if another program has the file open;
- keeps two more copies, `settings.json.bak` and one inside the database;
- never overwrites a damaged file. It is renamed `settings.json.broken-<time>`, the settings come back from a copy, and admin shows a notice.

The database writes every save to disk before Save reports done (SQLite WAL with `synchronous=FULL`). It is checked at start-up and copied once a day to `backups\`.

## Fixing a wrong vehicle number (or waste type, material, destination)

Operators can't change a saved trip. They press **Ask to correct (52)** on screen 5. The admin then fixes it:
- **One trip:** open admin, go to **Reports → 64 Trips**, find it by vehicle or ticket (the status filter **Asked** lists the requests), and press **Fix**. Change the vehicle number, From/Waste or Material/Going to, and give a reason. The ticket number stays the same.
- **A number typed wrong on many trips:** in Admin settings, use *Fix a vehicle number everywhere*. Every trip and the vehicle's empty weight move to the right number. If the right number already exists, the two are merged.

Every change keeps the old value. Click a trip to see its photos and its "Changed by admin" history. Fixed trips are marked *fixed* and re-sent to the cloud.

## Remote camera view (from anywhere)

See the cameras and the live weight from another city, with nothing opened on the plant's router, and very little internet:

```
 viewer's browser  ──►  relay (cloud_api on Cloud Run)  ◄──  plant PC asks "anyone watching?"
                          ▲                                   every 20 s (a few hundred bytes)
                          └──────── small JPEGs, only while someone is watching ────────┘
```

1. Deploy `cloud_api` (below) with a key for each site and keys for viewers:
   ```bash
   gcloud run deploy iswm-api --source cloud_api --region asia-south1 --allow-unauthenticated \
     --max-instances 1 --timeout 3600 \
     --set-env-vars "API_KEYS=owner:VIEWER-KEY,PLANT_KEYS=iswm-donthali:SITE-KEY,LIVE_MAX_MINUTES=10"
   ```
   `--max-instances 1` is needed because the relay passes pictures through memory.
2. In ISWM admin → *Remote camera view*: tick **Turn on**, paste the relay address (`https://iswm-api-….run.app`) and the site key, then save.
3. Open `https://iswm-api-….run.app/live/iswm-donthali?key=VIEWER-KEY` on any computer or phone. Choose Front, Back or Both, and Low data, Normal or Sharper.

| | Internet used at the plant |
|---|---|
| Nobody watching | about 1–2 MB a day (the "anyone watching?" question every 20 s; 1 minute gives about 0.5 MB a day) |
| Watching one camera, Normal (640 px, 1 picture a second) | about 0.1–0.2 GB an hour |
| Low data (480 px) | about half of that |

A view pauses after 10 minutes (`LIVE_MAX_MINUTES`), so a forgotten browser tab can't use data all day. Cost: Cloud Run only runs while requests are open, so it's normally inside the free tier. The plant's cameras run only while someone is watching.

## Live cameras on another computer

**Built-in (easiest, same network).** In admin, under *Live view for other computers*, tick **Turn on**, set a viewer password and save. Admin then shows the address, for example `http://192.168.1.20:8090`. Open it in any browser on another PC or phone on the same network, with user `viewer` and the password you set. The page shows all cameras, the live weight and today's trips.

ISWM is the relay, so the cameras are opened only once, by the plant PC, no matter how many people watch, and only while someone is watching. The cameras' own passwords never leave the plant PC. Up to 16 streams at a time, at about 6 pictures a second.

The installer allows this through the Windows firewall on **private** networks only. If the PC's network is set to *Public*, change it to *Private* in Windows network settings.

**From outside the plant (internet).** Use *Remote camera view* above. Or, with no cloud set-up at all: don't open a port on the router. Install [Tailscale](https://tailscale.com) (free) on the plant PC and on the viewing PC or phone, and sign in to both with the same account. Then use the plant PC's Tailscale address, for example `http://100.x.y.z:8090`, from anywhere. The connection is encrypted and needs no router changes.

**Full quality for a big screen or many viewers.** The built-in page sends ISWM's light preview. For full-resolution video on a control-room screen, let the cameras or NVR serve it directly: open the RTSP main stream in VLC, use the NVR's own app (Hik-Connect, DMSS), or run [MediaMTX](https://github.com/bluenviron/mediamtx) or [go2rtc](https://github.com/AlexxIT/go2rtc), which re-stream RTSP to browsers over WebRTC with low delay.

## The app window

ISWM is a normal standalone program. Its window has its own built-in browser engine (Qt WebEngine, part of the download), so it needs neither Edge nor .NET. It shows the plant icon and site name, with no address bar and no right-click menu, and it can't be navigated away from the app. Closing it stops ISWM, and starting ISWM a second time just says it's already open. The version is at the bottom-left of the sign-in screen (`ISWM.exe --version`).

If the built-in window can't start, for example with a very old graphics driver, ISWM uses a Microsoft Edge app window, and then the default browser. `ISWM.exe --software` starts the built-in window without the graphics card. `ISWM.exe --check` writes the result of a window test to `logs\iswm.log`.

**Weighbridge and the window.** The COM port is read by ISWM's own background reader, not by the window. The window only shows the reading, about 5 times a second, over the PC's internal connection, so it adds no lag and can't drop readings. What can cause trouble is the same as with any weighbridge program:
- another program holding the COM port (only one program can open it);
- a USB-to-serial adapter going to sleep (turn off *USB selective suspend* in Windows power options);
- the COM number changing when the adapter is moved to another USB socket;
- a wrong baud rate or regex.

**Is the weighbridge connected?** The top bar shows a green **Bridge on** pill, and a green dot next to the weight blinks with every reading that arrives. Blinking means data is coming in, even when the bridge is empty and shows 0. A dot that stops blinking, or a red **Bridge off**, means no data.

**The screen fits any monitor.** The layout is designed for 1366 × 620 and scales to the window: a wider screen gets wider boxes, a taller one gets bigger camera pictures. The full-view button makes the window full-screen.

## 7 Settings (for the tech team)

The **7 Settings** tab (Alt + 7) is open to everyone, so a technician can check things without the admin password:
- **Weighbridge:** connected or not, the live weight, readings per second, the **COM port**, a **Refresh** button that lists the COM ports on this PC, and the **last raw line** received from the indicator (useful when the weight pattern is wrong);
- **Cameras:** every camera with its type, **IP address and port**, status (Live / Off / Problem with the error), resolution, and a **Check** button that shows its picture.

With admin unlocked, the COM port and camera IP/port can be changed here and saved. Saving a COM port also turns the simulator off. Baud rate, parity, stop bits, weight pattern, camera endpoints, user names and passwords stay in Admin.

## Admin (hidden from operators)

Operators never see admin controls. To open them, press **Ctrl + Shift + A**, or tap the **site name 5 times** (top-left, or the big name on the sign-in screen), then type the admin password. A black **gear** button (admin settings) and a **padlock** button (lock admin) then appear in the top bar. Admin locks itself after 15 minutes without use, and five wrong passwords block tries for a minute.

Only the admin can change:
- site name, company and **logo** (PNG/JPG/WebP, under 2 MB, shown on the sign-in screen and top bar);
- operators and their PINs (each operator needs their own PIN; easy PINs like 1111 or 1234 are refused);
- the admin password (8+ characters, letters and numbers, must not contain an operator's PIN);
- weighbridge, cameras, Google Cloud sync, ticket serials and the reports folder.

**More cameras.** Admin → *Cameras* → **Add camera** (up to 8 in all). Each camera has a name shown on screen, a **Show on weighing screens** tick and a **Take photo at Save** tick. Front and back can't be removed; added cameras can. The weighing screens arrange the shown cameras so each picture is as big as possible. Front and back keep their support codes (12/13, 22/23, 42/43); added ones show C3, C4, …. Every camera with *Take photo* on is photographed at Save, and a trip's photos all appear when it is opened in Reports. The live-view page and the remote view list all cameras.

There are no default passwords or PINs.

## Keyboard only, or mouse only

Everything works with just a keyboard or just a mouse. Press **F1** in the app to see the keys.

| | Keyboard | Mouse only |
|---|---|---|
| Sign in | ← → pick your name (the last person is already picked); type the PIN on the number row or number pad. Backspace undoes, Delete clears. | Tap your name, tap the PIN keys |
| Change screen | Alt + 1 … 7 | Tap the tabs |
| Vehicle | Just start typing. ↑ ↓ choose, Enter picks | Tap the box and pick from the list; for a new number, turn on the keyboard button |
| Save | Enter again in the vehicle box once the weight is steady, or Ctrl + S | Tap Save |
| Inward From / Waste | Alt + R / C, Alt + M / W / D | Tap |
| Outward | Enter moves Vehicle → Material → Going to; type a material's first letter; Alt + K small scale | Tap |
| Other boxes and buttons | Tab / Shift + Tab, Enter or Space | Turn on the **keyboard button** in the top bar; then tapping a typing box shows an on-screen keyboard beside it (a number pad for weights) |
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

For the installer as well, install [Inno Setup 6](https://jrsoftware.org/isdl.php), then run `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ISWM.iss`. The result is `dist\ISWM-Setup.exe`.

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
| `iswm/cloud.py` | Batched Firestore sync (REST, no background traffic), optional photo upload |
| `cloud_api/` | Shared read-only real-time API for Cloud Run, plus Firestore rules |
| `iswm/service.py` | One method per UI action |
| `iswm/server.py` | Local HTTP server on 127.0.0.1 with a per-launch token, camera frames |
| `iswm/main.py` | Starts everything and opens the window |
| `iswm/window.py` | The standalone window (Qt WebEngine), Edge fallback, one-ISWM-per-PC |
| `iswm/remote.py` | Remote camera view: asks the relay if anyone watches, sends pictures only then |
| `installer/ISWM.iss` | Inno Setup script for `ISWM-Setup.exe` |
| `iswm/maintenance.py` | Daily database backup and clean-up of old photos, reports and logs |
| `iswm/liveview.py` | Password-protected live page for other computers (cameras, weight, today's trips) |
| `web/` | The screens: React + htm, using the Tharuni design-system bundle, offline |
| `project/`, `chats/`, `HANDOFF.md` | The original Claude Design handoff |

## Not in the prototype, added here

- First-run **Set up the plant** screen. Hidden admin settings, with a lock.
- Logo upload.
- **End shift** under the operator's name.
- A red **Not saved** line when the app refuses a save.
- Sync shows **Sync off** until it is set up.
- Download writes two CSVs, the summary and every trip, and offers **Open folder**.
- Reports: Daily shows today's trips with vehicle numbers. **64 Trips** searches by date, vehicle, ticket and status, with photos and admin **Fix**. **63** can summarise by vehicle.
- Live view page for other computers. Daily backups. Automatic clean-up.
