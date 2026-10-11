# ISWM Plant App

A Windows desktop app for the ISWM Donthali weighbridge. It's built from the Claude Design prototype `project/ISWM Plant App.dc.html`. The hardware code is adapted from [tsaaii/adex_lite](https://github.com/tsaaii/adex_lite).

- **Screens:** 1 Inward · 2 Outward · 3 Material recovery · 4 Tare · 5 Sync · 6 Reports, plus PIN sign-in and an admin settings page.
- **Weighbridge:** serial (COM port) or `socket://ip:port`. The weight is pulled out of the indicator's text with a regex and multiplier, as in adex_lite. A built-in simulator lets you test without hardware.
- **Cameras:** front and back, as a USB index, RTSP URL or HTTP snapshot URL. Live preview has zoom (− / + / mouse wheel). Save stores watermarked JPEGs.
- **Records:** stored in SQLite in `ISWM_data\` next to the .exe. Tickets are `IN{R|C}YYMM####` for inward and `O YYMM####` for outward. Each direction has one counter that never resets, so a ticket number can't repeat.
- **Sync:** uploads to Google Cloud Storage in the background as `agency/site/date/{entries,tares,batches,samples,corrections,images}/…`. The app keeps working offline.
- **Reports:** Daily, Shift (shift times can be changed), Incomplete, and Hourly/Daily/Weekly/Monthly with CSV download.

## Get the .exe

Each push runs the **Build Windows exe** GitHub Action. It runs the tests, builds with PyInstaller, and uploads `ISWM-windows.zip` as a build artifact under *Actions → run → Artifacts*. Pushing a tag such as `v1.0.0` also attaches the zip to a GitHub Release.

Unzip it anywhere and run `ISWM\ISWM.exe`. It needs Microsoft Edge WebView2, which is already on Windows 10/11.

To build by hand on Windows:

```bat
pip install -r requirements.txt pyinstaller==6.13.0
pyinstaller --noconfirm ISWM.spec
```

## First run

1. Sign in as **Operator 1** with PIN **0000**.
2. Click the gear icon and enter admin PIN **0000**. In admin settings:
   - Change the admin PIN, then add the operators with their own PINs.
   - **Weighbridge:** turn off *Simulate*, then pick the COM port, baud rate, data bits, parity and stop bits. Change the regex only if the indicator's output needs it. *Check again* shows the live reading.
   - **Cameras:** choose USB (with its device number), RTSP (`rtsp://user:pass@ip:554/stream1`) or HTTP snapshot for each camera.
   - **Sync:** turn it on and enter the bucket name and the full path to the service-account `.json` key. The key needs *Storage Object Admin* on that bucket.
   - **Ticket serials:** to continue from an older system, set the next inward and outward serial. They can only go up.
3. Click **Save settings**.

The simulator ships switched on, so the app works straight away for training. **Turn it off before real use.** While it's on, the weights are not real.

## Rules the app enforces

- Each vehicle gets one empty (tare) weight for its whole life. An inward trip from a vehicle with no tare is saved with its gross and stays *incomplete* until the vehicle is weighed empty on screen 4.
- Outward needs a vehicle that already has a tare, or a small-scale manual weight with a reason; manual entries are marked.
- Save takes the weight and both photos together. It works only when the weight is steady (within the set kg for the set seconds) and above the minimum (default 10 kg). This guards against misclicks.
- Net weight counts in reports only for complete records, meaning ones with both gross and tare.
- Saved entries are never edited in the app. Operators use **Ask to correct (52)**, and the request is uploaded for the admin.

## Run from source

```bash
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
| `web/` | The screens: React + htm, using the Tharuni design-system bundle, offline |
| `project/`, `chats/`, `HANDOFF.md` | The original Claude Design handoff |

## Not in the prototype, added here

- Admin settings page (gear icon) for hardware, operators, PINs, sync and serials.
- **End shift** under the operator's name.
- A red **Not saved** line when the app refuses a save, using the same plain wording.
- Sync shows **Sync off** until it is set up.
- Download writes two CSVs to the reports folder, the summary table and every trip, and offers **Open folder**.
