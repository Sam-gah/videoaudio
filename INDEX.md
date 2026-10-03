# Editor Desk: project index

Start here after cloning [Sam-gah/videoaudio](https://github.com/Sam-gah/videoaudio).

## For the editor

- [Windows setup and editing workflow](GUIDE.md): install once, launch locally, choose source folders, check sync, preview the grade and prepare clips.
- [Dashboard](index.html): the HTML application. Run Start_Windows.bat to open the working app; viewing this file on GitHub shows its source, not a running editor.
- [Windows setup script](Setup_Windows.bat): installs matching libraries and Windows FFmpeg into the local vendor folder.
- [Windows launcher](Start_Windows.bat): starts the local service and opens the browser.
- [Overview and limitations](README.md): what this app does and does not do.

## For the developer or next Codex session

- [Technical handoff and approved reference settings](CODEX_HANDOFF.md): verified audio offsets, selected ranges, the natural grade, prior fixes, QA and unfinished work.
- [Local service](app.py): media import, playback, saved settings, matching suggestions and preparation jobs.
- [Browser behavior](app.js), [layout](index.html), [styles](style.css).
- [Regression tests](test_app.py) and [dependencies](requirements.txt).
- [Product brief](PRODUCT.md) and [design decisions](DESIGN.md).

## Reference assets and drive scope

- [Approved Trudent S-Log3/S-Gamut3.Cine LUT](assets/approved_trudent.cube): lighting-specific reference, not a universal grade.
- [Aggregate drive snapshot](drive_inventory.js): 660 video files, 98 recordings and 905 photos, including backups or duplicates.
- [Read-only inventory scanner](inventory_drive.py): updates the snapshot from the editor's actual drive location.
- [FFmpeg license information](tools/FFMPEG_LICENSE.txt).

Only the six Trudent test clips were prepared previously. Other footage still needs client sorting, source-profile checks, audio matching and human approval. **GitHub contains no client media or finished videos.** The developer/editor receives those separately on Transcend and selects their locations in the app.
