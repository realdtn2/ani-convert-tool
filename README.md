# ani-convert-tool

A Python tool for extracting data from `.ani` cursor files and converting them into standard animated formats.

It reconstructs the `.ani` cursor file with the correct animation timing, frame order, and playback behavior as defined inside the ANI file into standard animated formats with near-exact accuracy.

---

## Features

- Extracts all ANI metadata into a readable `manifest.json`
- Dumps embedded frames (`.ico` / `.cur`) without modification
- Rebuilds animations using internal timing and sequence data
- **Batch processing support** - convert entire folders of ANI files at once
- **Smart output handling** - auto-generates filenames and creates unique folders
- Supports multiple output formats:
  - GIF
  - WEBP
  - MP4
  - MOV
  - AVI
  - MKV

---

## Requirements

- Python 3.8+
- Pillow (for GIF / WEBP)
- MoviePy + NumPy (for video formats)

Install dependencies:

```bash
pip install pillow moviepy numpy
```

---

## Usage

### Extract ANI contents

**Single file:**
```bash
py main.py e file.ani [output_dir]
```

**Batch (entire folder):**
```bash
py main.py e cursors/ [output_dir]
```

If no output directory is given, a new folder is auto-generated:
- Single file: `filename/`
- Folder: `foldername_extracted/`

---

### Convert ANI to animation

**Single file:**
```bash
py main.py c <format> file.ani [output] [--keep|-k]
```

**Batch (entire folder):**
```bash
py main.py c <format> input_folder/ [output_folder/] [--keep|-k]
```

**Supported formats:**
```
gif, webp, mp4, mov, avi, mkv
```

**Examples:**

```bash
# Single file - auto-named output
py main.py c gif cursor.ani

# Single file - custom output
py main.py c webp cursor.ani cursor.webp

# Single file - keep temp files
py main.py c mp4 cursor.ani --keep

# Batch conversion - auto-named output folder
py main.py c gif cursors/

# Batch conversion - custom output folder
py main.py c gif cursors/ output/

# Batch with organized temp files
py main.py c mp4 animations/ videos/ --keep
```

**Behavior:**

* Frames are extracted to a temporary folder
* The animation is rebuilt using the ANI sequence and timing data
* Output files are written with unique names (appends `_1`, `_2`, etc. if file exists)
* Temporary files are deleted unless `--keep` is specified
* When using `--keep` in batch mode, all temp folders are organized in `temp_extractions/`
* Missing file extensions are automatically appended

---

## Flags

- `-h`, `--help` - Show help message
- `-k`, `--keep` - Keep temporary extraction folders
  - Single file: temp folder saved alongside output
  - Batch: all temp folders organized in `output_dir/temp_extractions/`

---

## Help

```bash
py main.py --help
```

---

## Output Details

* Timing is derived from ANI jiffy values (1/60 second units)
* Repeated frames in the sequence are preserved
* GIF durations are rounded to valid frame ticks (10ms minimum)
* Video outputs use a fixed 60 FPS timeline
* Output folders are automatically created with unique names if they already exist

---

## Files Generated

**When extracting:**

```
output_dir/
├── frame_000.ico
├── frame_001.ico
├── ...
└── manifest.json
```

**When batch extracting:**

```
output_dir/
├── cursor1/
│   ├── frame_000.ico
│   └── manifest.json
├── cursor2/
│   ├── frame_000.ico
│   └── manifest.json
└── ...
```

**When batch converting with --keep:**

```
output_dir/
├── temp_extractions/
│   ├── cursor1/
│   └── cursor2/
├── cursor1.gif
├── cursor2.gif
└── ...
```

**The manifest contains:**

* Animation header (`anih`)
* Frame list
* Playback sequence
* Per-step rates (if present)
* Embedded metadata

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

This is a personal project, but bug reports and suggestions are welcome via issues.