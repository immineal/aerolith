# bryce_harness

Drives a Windows 98 SE QEMU VM (with Bryce 2 for Windows) from the host through QMP. It handles
screenshots, keyboard, mouse, CD/floppy swaps, snapshots, and file transfer.

## How it works

| Need | Mechanism |
|---|---|
| See the screen | QMP `screendump` (PNG); the Cirrus hardware cursor is included in the frame |
| Keyboard | QMP `input-send-event` key events (qcodes, US layout) |
| Mouse | Relative PS/2 motion. Win98 has pointer acceleration off (registry, set at install), so 1 count = 1 pixel. Every absolute move first slams the pointer into the top-left corner (`home`), then moves relatively, so no drift accumulates. `bry pointer x y` verifies closed-loop by diffing frames. |
| Guest → host files | Guest saves to `D:\` (transfer disk). `pull` does a QMP `blockdev-backup` of that disk (consistent point-in-time copy, VM keeps running) and reads it with mtools. Write-behind caching is disabled in the guest. |
| Host → guest files | `push` builds a Joliet ISO and inserts it as the CD (`E:\`). |
| Known states | `savevm` / `loadvm` internal qcow2 snapshots (all disks + RAM) |
| Two clients | QEMU serves one client per QMP socket; there are two (`qmp.sock`, `qmp-watch.sock`) and the client falls back to whichever is free. Background watchers should connect per action and close. |

## CLI (`./bry ...` from the project root)

```
start [--loadvm NAME] [--cdrom ISO] [--tcg] [--cache unsafe]     stop | status
shot [OUT] [--crop x0,y0,x1,y1] [--zoom N] [--grid STEP] [--stable]
wait [--settle S]                     # until the screen is stable
key ret alt-f4 ctrl-s ...             type "literal text"
click X Y | dclick X Y | rclick X Y | move X Y | drag X0 Y0 X1 Y1
pointer X Y                           # where did the cursor really land?
ocr [--crop ...] [--words]   findtext TEXT   clicktext TEXT [--double]
run "command line"                    # Start > Run
push FILE...                          pull 'D:\path' host_dest     xls 'D:\'
cd ISO|eject   floppy IMG|eject
savevm NAME   loadvm NAME   snapshots   hmp "info ..."
selftest                              # pointer, keyboard, both transfer directions
```

Screenshots without an explicit path go to `vm/run/shots/`.

## Bryce layer (`bryce.py`, `probe.py`)

Bryce 2 draws one light-grey palette frame centred on a black desktop. The frame grows with the
document size, so everything is located relative to the frame's top-left corner, which
`frame_box()` finds in each screenshot.

- **Hover labels are the ground truth.** When the pointer is over a control, Bryce prints its name in
  the bottom-left corner of the frame: a group title in large type ("Render") and the control name in
  small type ("Fast Preview Mode"). `read_label()` OCRs both lines. `probe.py` hover-scans a
  region on a grid and writes every label's position, which is how `ui_map.json` was built.
  `ui_click()` hovers first and refuses to click if the label doesn't match.
- **Render completion.** While rendering, Bryce draws a 1-px light scan line across the view.
  `wait_render()` returns once that line has been gone for 3 samples and the view stops changing.
  It never sends input, because any key or click stops a Bryce render.
- **Focus.** Keyboard shortcuts only reach Bryce after a click on the black desktop (`focus()`).

```
frame                                  # frame + view boxes
label [X Y]                            # Bryce's hover label (after moving to X,Y)
ui --list | ui NAME [--move|--double]  # click a mapped control, hover-verified
probe x0,y0,x1,y1 [--step 8]           # map a frame-relative region by hovering
open 'E:\SAMPLE\...\X.BRC'             render [OUT] [--no-wait]    waitrender [OUT]    rendering
```

Win98 power management has "turn off monitor" set to Never. A blanked screen shows up as a 720x400
black text-mode frame, and waking it with a key would abort a render.


## Wine backend (production)

`winebox.py` runs the same Bryce2.exe under Wine on a private Xvfb display at native speed, with
the same input and screen interface as the VM, so `bryce.py` works on either. `sheet.py` builds
scenes directly as `.brc` files (`brc.py`, format in `docs/brc-format.md`), renders them with
Render to Disk on a pool of Bryce instances (one Wine prefix and display each, `POOL`), and
mattes the three passes per sprite:

| Pass | Backdrop | Used for |
|---|---|---|
| K | black | colour and the light the object adds |
| W | mid grey (0.5) | transmission: how much of the backdrop shows through glass |
| M | black, objects as flat red (solid) / green (glass) | coverage and which matte applies |

Bryce is restarted for every job and `wineserver -k` runs after it, because an idle Bryce keeps
burning a core. Expected local layout (not in this repository; bring your own Bryce 2):

```
wine/prefix*      one WINEPREFIX per pool instance
wine/bryce2       the Bryce 2 program folder
work/             exchange folder (W:\ inside Bryce): scenes in, BMP renders out
```

## Watching renders

`tools/watch.py` shows every pool display (`POOL`) live in a browser, plus a history of finished
renders, read-only:

```
python3 harness/tools/watch.py            # http://127.0.0.1:6080/ ; --port, --displays :77,:78
kill <PID>                                # the PID is printed on start; stop it by PID
```

**Live view.** One tile per Xvfb display (click a tile for full size, refresh 1/2/5 s). Frames are
plain X11 screenshots (Pillow `ImageGrab`) taken only while a browser asks for them, so an unwatched
viewer costs nothing. A black tile means the instance is idle: Bryce is stopped between jobs while
its Xvfb stays up.

**Render history** (the "Recent renders" section; the `view` selector switches between live,
history and both). Newest first, polled every 4 s, 24/48/96 cards, filter by source:

- `work/lib/` (render cache): the `<name>_k/_w/_m.bmp` passes (black, white, mask) are grouped into one card.
- `work/sheets/` (older lookdev renders, NTFS archive, scanned only every 15 s) and
  `library/dist/sprites/` (PNG/WebP; the `@2x` variant is shown, the others are links).
- Click a thumbnail for the full-size image (BMP is served as PNG), click again for 1:1, arrow keys
  step through, Esc closes. Override the directories with `--lib`, `--sheets`, `--sprites`.
- Endpoints: `/renders.json?src=all|lib|sheets|sprites&n=48`, `/thumb/<src>/<file>?w=240`,
  `/full/<src>/<file>`. Only files that were listed (regular files directly inside those three
  directories, `.bmp/.png/.webp`) can be fetched; anything else is a 404.
- Thumbnails and full-size PNGs are made with Pillow on request and kept in a 64 MB in-memory LRU
  keyed by path and mtime. Nothing is written to disk, least of all to `work/lib`.
- Cost: one `os.scandir` per directory every 3 s (about 13 ms CPU for `work/lib`), and only while a
  browser polls; after 30 s without a request the scanners stop touching the disk. A file is listed
  only once its size and mtime are unchanged since the previous scan and its header says it is
  complete (BMP pixel data, PNG `IEND`, WebP length), so a new render shows up 3 to 6 s after it is
  written. The process runs at nice 10 and converts one image at a time.

Neither view has any input path: nothing is sent to Xvfb, Wine or Bryce, so it is safe to run
during renders. It binds to 127.0.0.1 only and rejects other `Host` headers; to see it from
another machine use an SSH tunnel (`ssh -L 6080:127.0.0.1:6080 host`).

## Win98 VM backend (the authentic reference)

Before the Wine path, Bryce 2.1 ran in a Windows 98 SE QEMU VM driven by this harness. It is
kept as the reference for how Bryce really behaves. The local layout it expects (none of it is
in this repository; you need your own Windows 98 and Bryce 2 media):

```
media/        installers: Win98 SE CD, Bryce 2 CD (Win95/NT + Mac hybrid)
build/        scripts that rebuild the VM from scratch (make_disks.sh, msbatch.inf, install_win98.py)
vm/           disk images (c.qcow2 = Win98 + Bryce, xfer.qcow2 = transfer disk D:), run/ = sockets, logs, shots
harness/      this package
bry           CLI wrapper: ./bry <command>
```

Watch the VM live with `vncviewer localhost:5905`.
