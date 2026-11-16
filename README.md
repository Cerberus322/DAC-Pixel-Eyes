# DAC Pixel Eyes

Animated eyes, short retro-game scenes and a keyboard-triggered clock for a SteelSeries OLED base station, through SteelSeries GG / GameSense.

**Windows x64 test release: v0.1.2-test.** This is an independent, AI-assisted personal project. It is not affiliated with or endorsed by SteelSeries.

## Download and run

1. Open this repository's **Releases** section.
2. Download **DACPixelEyes-v0.1.2-test-windows-x64.zip** from the release assets. GitHub's automatic **Source code** downloads do not contain the executable.
3. Extract the entire ZIP. Keep the executable and its `_internal` folder together.
4. Keep SteelSeries GG running and connect the base station to your Windows PC by USB.
5. Open `DACPixelEyes/DACPixelEyes.exe`.

No Python installation is needed for the packaged app. For an optional per-user installation with Start menu and desktop shortcuts, run the included `Install.ps1` from the extracted release folder. The portable executable works without installation.

## Display profiles

| Profile | GameSense output | Status |
| --- | --- | --- |
| GameDAC / Arctis Nova Pro | 128×52, 832 bytes | Tested on the original wired Arctis Nova Pro / GameDAC setup |
| **Arctis Pro Wireless (Test)** | 128×48, 768 bytes | Experimental: software payloads tested, physical wireless base station not yet verified |

**Arctis Pro Wireless is not Arctis Nova Pro Wireless.** The experimental button is for the older **Arctis Pro Wireless** base station. It does not establish compatibility with Nova Pro Wireless, Nova Pro Omni, other headset models, or consoles.

Select a profile and click **Save & apply**. The app redraws the same animations at the selected output size and rebinds the GameSense event. The 128×48 profile scales vertically using nearest-neighbor sampling; it does not crop away the clock or game edges. Switch back to the default profile if testing does not display an image.

## Features

- Blinks and occasional looks, with quiet time between actions.
- Curious, confused and laughing expressions.
- Pong, Breakout, racing, Space Invaders-style scenes, Tetris-style scenes, Snake, eye ping-pong and a cowboy duel. These are automatic animations, not playable games.
- Local PC time in 24-hour `HH:MM` format. The eyes return to center, transform into the clock, and return to normal.
- A configurable global keyboard shortcut. The default is `|`; alternatives such as `Ctrl+Alt+T` are supported when not already reserved by another app.
- Speed, clock duration, per-animation switches, tray controls and optional **Start with Windows**.
- Automatic reconnection to GameSense and one running instance per Windows session.

## Smoothness and performance

Basic / Normal / High target 15 / 30 / 60 FPS. Pong and looks are generated as continuous movements; the remaining games and expressions retain their original animation frames.

The window reports the rate of frames **sent to GG**, not the physical OLED refresh rate. Actual device output can be much slower. On the original test setup, animated image submission was around 6 FPS during Pong. Selecting High does not guarantee 60 FPS on the device.

**Compare Basic and High** runs the same look and Pong sequence at 1× speed, then restores your settings. Your clock shortcut can interrupt the comparison.

## Settings and tray

- Click **Save & apply** after changing settings.
- **Capture shortcut** records a single key or a Ctrl / Alt / Shift combination.
- Closing the settings window keeps the app running in the notification area.
- Right-click its tray icon to reopen settings, show the clock, pause, or exit.
- **Start with Windows** is off by default for new users. It starts the app in the background at sign-in when enabled.
- **Open logs folder** opens `%LOCALAPPDATA%\DACPixelEyes`, containing `settings.json` and rotating `app.log` files.

The app does not log typed text or upload telemetry. It sends images and GameSense events to GG on the local machine. Log files may contain local paths and error details: review them before sharing a bug report.

## Troubleshooting and test reports

1. Check that GG detects the device and that the display profile matches the exact headset model.
2. Ensure this integration is enabled under GG → Engine → Apps. The app is registered as **DAC Pixel Eyes**.
3. Stop older test scripts or other copies sending images to the same display. Temporarily disable other OLED integrations such as NowPlaying to isolate conflicts.
4. A successful HTTP response confirms receipt by GG, not that the OLED displayed the image. If output becomes stuck, restarting GG and reconnecting USB helped on the original test setup; this can briefly interrupt audio.
5. For wireless testing, report the exact model, USB connection, GG version, chosen profile, whether the clock works, and what appears on the physical screen.

No firmware changes or direct USB writes are performed. A developer code signature is not included in this test build.

## Run or build from source

Tested with Python 3.15 on Windows x64.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\pythonw.exe src\app.py
```

To build the packaged executable:

```powershell
.\Build.ps1 -Python .\.venv\Scripts\python.exe
```

The result is `dist/DACPixelEyes/`. The build script also creates the downloadable test ZIP and checksum in `release/`.

## Credits and project status

This project was developed with substantial AI assistance. The robot-eyes concept was inspired by examples from [FluxGarage / RoboEyes](https://github.com/FluxGarage/RoboEyes). This app uses its own Python rendering and GameSense client rather than the Arduino library.

GameSense documentation: [SteelSeries GameSense SDK](https://github.com/SteelSeries/gamesense-sdk).

The application is being shared for community testing. Multi-day reliability and additional hardware compatibility are still being evaluated. No official SteelSeries catalog listing is claimed.
