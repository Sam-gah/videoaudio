# Editor Desk

Offline HTML dashboard plus a local Python service. No subscriptions, accounts, cloud uploads or API charges. This is a preparation/handoff tool, not a replacement for the human editor.

Start with the [project index](INDEX.md) or [Windows editor/developer guide](GUIDE.md). The [HTML dashboard](index.html) runs locally after launching the app. For the approved technical settings and previous fixes, read [CODEX_HANDOFF.md](CODEX_HANDOFF.md).

## Cloning from GitHub

The Git repository contains the application, approved Trudent LUT and CODEX_HANDOFF.md, **not the client videos, recordings, finished exports or machine-specific catalog**. Clone it to the editor's laptop or a writable folder on Transcend. On Windows, run Setup_Windows.bat once and then Start_Windows.bat. The first launch creates a fresh local client library and catalog. Use Import folders to choose the video/audio locations already on the hard drive. Imported media, rendered files, saved notes and installed dependencies are ignored by Git and remain private on that computer/drive.

The original six-clip Trudent media library exists only in the owner's full working folder. The detailed MD preserves the verified matches and technical work. Cloning the code does not transfer those files or mean any new-client clips have already been prepared. Open index.html directly only after the first app launch has generated catalog.js.

Repository: https://github.com/Sam-gah/videoaudio. It is public. No media, detailed filename inventory, generated catalogs, credentials or device settings are committed. The Drive inventory view contains only folder-level counts from the read-only scan; it is not proof those files are unique or processed.

## Full-drive scope

The six supplied videos were a test batch, not the full project. A read-only scan of production bichitras found **660 video files, 98 audio files, and 905 photos**, about 127.4 GiB total including sidecars/other files. Folder counts: tru dent 121 videos; tru dent + hygenic clips + photos 204 videos and 905 photos; trudent backs 335 videos; tru dent audio 98 recordings. Counts include backups/proxies/duplicates, not a deduplicated list of unique takes. Only six Trudent clips were matched/finished previously. New footage must be sorted by actual client, profile, lighting and dialogue coverage. The app has no six-video processing cap.

The full filename manifest is private in drive_inventory.json on the owner's computer, excluded from Git. drive_inventory.js is the public aggregate snapshot shown in the app. To rescan on Windows: `py -3 inventory_drive.py "E:\production bichitras"`, changing the drive letter. This reads metadata and writes the manifest locally, never to the source folders.

## Start

Mac: double-click `Start_Mac.command`. If macOS denies execution, use Terminal: `python3 app.py` from this folder. Windows: install Python 3.10+ with pip first, run `Setup_Windows.bat` once while connected to the internet, then double-click `Start_Windows.bat`. Setup downloads matching libraries and the correct Windows FFmpeg into this app's vendor folder, not your global Python environment. Afterwards the app works offline. Keep the terminal open while working. Close it or press Ctrl+C to stop. The app listens only on `127.0.0.1`, normally port 8765. It opens your browser automatically.

For viewing only, double-click `index.html`. The supplied catalog and media still work offline; importing, saving review notes, matching and rendering require the local service. Browser codec support varies; use the H.264 1080p files for the most compatible previews.

## Folder layout

```
Editor_Desk/
  index.html, app.py, Start_Mac.command, Start_Windows.bat
  assets/approved_trudent.cube
  tools/ffmpeg-mac-arm64
  projects/
    trudent/
      video/       six original camera videos
      audio/       original separate recordings and clean-dialogue WAVs
      final/       4K masters and 1080p exports, organized by clip
      reports/     original match evidence, manifests and QA
      project.json review state and source-to-audio mapping
    client-2/      empty project, rename before importing
    client-3/      empty project, rename before importing
```

In the owner's seeded working copy, Trudent media are real regular files, not symlinks to the original drive. On this Mac, copy-on-write cloning is used when available to avoid consuming another full copy's worth of storage. Copy the entire working Editor_Desk folder to transfer that existing media library. That transfer needs roughly the folder's logical media size, even when your Mac currently shares storage blocks. Source-drive files remain unchanged. A Git clone is the code-only alternative described above. Do not copy only index.html if you want the working media handoff.

## Add a client

Use Add client, give it a name, enter a local camera-video folder and a separate audio folder, then choose Import folders. Import recursively copies only supported media and Sony XML sidecars into the chosen client's folders. It never moves originals. This is asynchronous; the jobs panel shows progress and failures. Paths must refer to folders on the computer running the local service. You can also place files directly inside a project's video/audio/final folders and choose Refresh. Camera identifiers may repeat between clients without mixing their recordings.

## Prepare a new clip

1. Select a video and Find audio candidates. Automatic matching needs optional packages: `python3 -m pip install -r requirements.txt` (Windows: `py -3 -m pip install -r requirements.txt`). It compares camera scratch audio with this client's separate recordings. It cannot identify a match if the camera has no usable scratch audio. Scores are suggestions, not approvals. Listen and check lips/transients before using a candidate.
2. Select a recording and enter the offset. Convention: **audio time = camera time + offset**. Negative offsets mean the recording starts after the camera. The app shows overlap coverage; set a camera in/out interval inside it. Each clip is continuous; there is no automatic story edit or time stretching.
3. Choose input profile explicitly. The approved Trudent LUT expects full-range S-Log3/S-Gamut3.Cine and contains Trudent-specific white balance/exposure choices. Do not use it on S-Gamut3, another log format or already-corrected Rec.709. New lighting requires visual judgment. Rec.709 bypass is available. Rotation is explicit and does not default to portrait for new footage.
4. Save settings. Generate grade preview and inspect skin/highlights. Prepare 1080p writes a new H.264 video and 48 kHz/24-bit cleaned WAV using conservative rumble/noise filtering, compression and two-pass -16 LUFS normalization. Noise-reduction timing is compensated by 25 ms. Partial audio is never silently stretched or padded to cover missing dialogue. Camera-audio fallback must be selected explicitly and is flagged.
5. Review the result and save a handoff note/status. The human editor handles scene-specific finishing, exact lip-sync approval, shot selection, story edits, captions, music and branding. New exports have not undergone the same full QA as the previously verified six Trudent clips; play them through before delivery.

New preparation exports are 1080p with the original aspect ratio (maximum 1920 pixels on the long side), H.264 CRF 17 and AAC. They do not replace existing 4K masters. Use the bundled LUT and clean WAV in the editor's NLE when a new 4K master is needed.

## FFmpeg / Windows

The included FFmpeg binary in this working library is for Apple Silicon Macs only. The small shareable starter ZIP excludes that binary. Windows Setup installs imageio-ffmpeg, which supplies a Windows binary; the app detects it automatically. Alternatively supply a compatible FFmpeg binary using Settings, place `ffmpeg.exe` (Windows) / `ffmpeg` inside tools/, or use a system FFmpeg on PATH. On an Intel Mac install requirements.txt for its native FFmpeg. No media upload occurs. The local Apple Silicon build reports GPL version 2 or later, not LGPL; its own license output and source links are in tools/FFMPEG_LICENSE.txt. Preserve and comply with the installed binary's accompanying license when redistributing it.

## Safety and limitations

The local service has an origin check and per-session write token. Do not expose it to the network or use it as a public server. Writes are confined to this app folder; imports read only folders you specify. Jobs are serialized and existing media are never overwritten by rendering or import. Free-space checks happen before large imports and renders. Disconnecting a drive can fail a job; reconnect and retry. Close the app only after jobs finish. Render failures leave an explicit job error and any partial outputs for inspection. This version is source-distributed, not a tested Windows .exe. An executable can be packaged later on the editor's actual operating system.
