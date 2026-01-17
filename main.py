# ani-convert-tool - ANI cursor file extractor and converter
# Copyright (C) 2026 realdtn
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import struct
import json
import os
import sys
import shutil
import numpy as np

# -----------------------------
# Optional support libraries
# -----------------------------
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    try:
        from moviepy.video.io.ImageSequenceClip import ImageSequenceClip
    except ImportError:
        from moviepy.editor import ImageSequenceClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

JIFFY_MS = 1000 / 60.0
JIFFY_SEC = 1 / 60.0

# Supported formats
SUPPORTED_FORMATS = {"gif", "webp", "mp4", "mov", "avi", "mkv"}
VALID_FLAGS = {"-h", "--help", "-k", "--keep"}

# -----------------------------
# File System Utilities
# -----------------------------

def get_unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        p = f"{base}_{i}{ext}"
        if not os.path.exists(p):
            return p
        i += 1

# -----------------------------
# RIFF utilities
# -----------------------------

def read_u32(f):
    return struct.unpack("<I", f.read(4))[0]

def read_fourcc(f):
    return f.read(4).decode("ascii", errors="replace")

# -----------------------------
# ANI parsing
# -----------------------------

def parse_anih(data):
    fields = struct.unpack("<9I", data[:36])
    return {
        "cbSizeof": fields[0],
        "cFrames": fields[1],
        "cSteps": fields[2],
        "cx": fields[3],
        "cy": fields[4],
        "cBitCount": fields[5],
        "cPlanes": fields[6],
        "jifRate": fields[7],
        "flags": fields[8],
        "AF_ICON": bool(fields[8] & 1),
        "AF_SEQUENCE": bool(fields[8] & 2),
    }

def parse_info_list(data):
    info = {}
    off = 0
    while off + 8 <= len(data):
        cid = data[off:off+4].decode("ascii", errors="replace")
        size = struct.unpack("<I", data[off+4:off+8])[0]
        val = data[off+8:off+8+size]
        info[cid] = val.rstrip(b"\x00").decode("utf-8", errors="replace")
        off += 8 + size + (size & 1)
    return info

def parse_dword_array(data):
    return list(struct.unpack("<" + "I" * (len(data)//4), data))

# -----------------------------
# Extract ANI
# -----------------------------

def extract_ani(path, outdir):
    with open(path, "rb") as f:
        if read_fourcc(f) != "RIFF":
            raise ValueError("Not RIFF")
        riff_size = read_u32(f)
        if read_fourcc(f) != "ACON":
            raise ValueError("Not ANI")

        os.makedirs(outdir, exist_ok=True)

        result = {
            "file": os.path.basename(path),
            "anih": None,
            "info": {},
            "rate": None,
            "sequence": None,
            "frames": []
        }

        frame_index = 0

        while f.tell() < riff_size + 8:
            cid = read_fourcc(f)
            size = read_u32(f)

            if cid == "anih":
                result["anih"] = parse_anih(f.read(size))

            elif cid == "rate":
                result["rate"] = parse_dword_array(f.read(size))

            elif cid == "seq ":
                result["sequence"] = parse_dword_array(f.read(size))

            elif cid == "LIST":
                list_type = read_fourcc(f)
                list_size = size - 4
                end = f.tell() + list_size

                if list_type == "INFO":
                    result["info"] = parse_info_list(f.read(list_size))

                elif list_type == "fram":
                    while f.tell() < end:
                        chunk = read_fourcc(f)
                        fs = read_u32(f)
                        data = f.read(fs)

                        if chunk == "icon":
                            ext = "ico"
                        elif chunk == "cur ":
                            ext = "cur"
                        else:
                            ext = "bin"

                        name = f"frame_{frame_index:03d}.{ext}"
                        with open(os.path.join(outdir, name), "wb") as o:
                            o.write(data)

                        result["frames"].append({
                            "index": frame_index,
                            "file": name,
                            "size": fs,
                            "type": ext
                        })

                        frame_index += 1
                        if fs & 1:
                            f.read(1)
                else:
                    f.read(list_size)
            else:
                f.read(size)

            if size & 1:
                f.read(1)

        with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as o:
            json.dump(result, o, indent=4)

        return result

# -----------------------------
# Image loader
# -----------------------------

def load_image(path):
    try:
        img = Image.open(path)
        try:
            img.seek(0)
        except Exception:
            pass
        return img.convert("RGBA")
    except Exception as e:
        raise RuntimeError(f"Cannot load image: {path}") from e

# -----------------------------
# Animation builder
# -----------------------------

def build_animated(manifest, folder, out_path):
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow required")

    ext = os.path.splitext(out_path)[1].lower()
    anih = manifest["anih"]
    seq = manifest["sequence"] or list(range(anih["cFrames"]))
    rate = manifest["rate"]

    images = [load_image(os.path.join(folder, f["file"])) for f in manifest["frames"]]

    # Expand frames
    expanded = []
    durations = []

    canvas_size = images[0].size

    for i, idx in enumerate(seq):
        j = rate[i] if rate else anih["jifRate"]
        frame = images[idx].copy()
        frame = frame.resize(canvas_size)
        expanded.append(frame)
        ms = j * JIFFY_MS

        # Round to nearest 10ms (GIF tick)
        ms = int(round(ms / 10) * 10)

        # Enforce sane minimum (prevents speedup)
        ms = max(ms, 20)

        durations.append(ms)

    # GIF / WEBP
    if ext in (".gif", ".webp"):
        expanded[0].save(
            out_path,
            save_all=True,
            append_images=expanded[1:],
            duration=durations,
            loop=0,
            disposal=2,
            optimize=False
        )
        return

    # VIDEO FORMATS
    if ext in (".mp4", ".mov", ".avi", ".mkv"):
        if not MOVIEPY_AVAILABLE:
            raise RuntimeError("MoviePy required")

        video_frames = []
        for i, idx in enumerate(seq):
            j = rate[i] if rate else anih["jifRate"]
            repeat = max(1, int(round(j)))
            frame = images[idx].convert("RGB")
            video_frames.extend([np.array(frame)] * repeat)

        clip = ImageSequenceClip(video_frames, fps=60)
        clip.write_videofile(out_path, codec="libx264")
        return

    raise RuntimeError(f"Unsupported output format: {ext}")

# -----------------------------
# Argument validation
# -----------------------------

def validate_args(args, start_idx):
    """Check for invalid flags in arguments after start_idx"""
    for arg in args[start_idx:]:
        if arg.startswith("-") and arg not in VALID_FLAGS:
            print(f"Error: Unknown flag '{arg}'")
            print(f"Valid flags: {', '.join(sorted(VALID_FLAGS))}")
            sys.exit(1)

def get_flags(args):
    """Extract and validate flags from arguments"""
    flags = [arg for arg in args if arg.startswith("-")]
    for flag in flags:
        if flag not in VALID_FLAGS:
            print(f"Error: Unknown flag '{flag}'")
            print(f"Valid flags: {', '.join(sorted(VALID_FLAGS))}")
            sys.exit(1)
    return flags

def get_non_flags(args):
    """Get non-flag arguments"""
    return [arg for arg in args if not arg.startswith("-")]

# -----------------------------
# Batch processing
# -----------------------------

def find_ani_files(path):
    """Find all .ani files in a directory"""
    if not os.path.isdir(path):
        return []
    return [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith('.ani')]

def process_batch_extract(input_dir, output_dir):
    """Extract all .ani files from input_dir to output_dir"""
    ani_files = find_ani_files(input_dir)
    
    if not ani_files:
        print(f"No .ani files found in '{input_dir}'")
        return
    
    # Get unique output directory name
    output_dir = get_unique_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Found {len(ani_files)} .ani file(s) in '{input_dir}'")
    print(f"Output directory: {output_dir}")
    successful = 0
    failed = 0
    
    for ani_path in ani_files:
        basename = os.path.splitext(os.path.basename(ani_path))[0]
        out_folder = os.path.join(output_dir, basename)
        # Don't use get_unique_path here since we're in a new directory
        
        try:
            extract_ani(ani_path, out_folder)
            print(f"  ✓ {os.path.basename(ani_path)} → {basename}/")
            successful += 1
        except Exception as e:
            print(f"  ✗ {os.path.basename(ani_path)} failed: {e}")
            failed += 1
    
    print(f"\nCompleted: {successful} successful, {failed} failed")

def process_batch_convert(input_dir, output_dir, fmt, keep=False):
    """Convert all .ani files from input_dir to output_dir"""
    ani_files = find_ani_files(input_dir)
    
    if not ani_files:
        print(f"No .ani files found in '{input_dir}'")
        return
    
    # Get unique output directory name
    output_dir = get_unique_path(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a temp folder for all extractions if --keep is used
    if keep:
        temp_base = os.path.join(output_dir, "temp_extractions")
        os.makedirs(temp_base, exist_ok=True)
    
    print(f"Found {len(ani_files)} .ani file(s) in '{input_dir}'")
    print(f"Converting to {fmt.upper()} format...")
    print(f"Output directory: {output_dir}")
    successful = 0
    failed = 0
    
    for ani_path in ani_files:
        basename = os.path.splitext(os.path.basename(ani_path))[0]
        
        if keep:
            # Keep temps organized in a subfolder
            temp = os.path.join(temp_base, basename)
        else:
            # Use unique temp folder in current directory
            temp = get_unique_path(f"temp_{basename}")
        
        out_file = os.path.join(output_dir, f"{basename}.{fmt}")
        # Don't use get_unique_path here since we're in a new directory
        
        try:
            manifest = extract_ani(ani_path, temp)
            build_animated(manifest, temp, out_file)
            
            print(f"  ✓ {os.path.basename(ani_path)} → {os.path.basename(out_file)}")
            successful += 1
        except Exception as e:
            print(f"  ✗ {os.path.basename(ani_path)} failed: {e}")
            failed += 1
        finally:
            # Clean up individual temp folder if not keeping
            if not keep and os.path.exists(temp):
                shutil.rmtree(temp)
    
    print(f"\nCompleted: {successful} successful, {failed} failed")
    if keep:
        print(f"Temp extractions saved in: {temp_base}")

# -----------------------------
# CLI
# -----------------------------

def show_help():
    print("""
Usage:
  py main.py e|extract <file.ani|folder> <output_dir>
  py main.py c|convert <format> <file.ani|folder> <output_dir> [--keep|-k]

Commands:
  e, extract     Extract ANI file(s) to folder(s)
  c, convert     Convert ANI file(s) to animated format

Formats:
  gif, webp, mp4, mov, avi, mkv

Flags:
  -h, --help     Show this help message
  -k, --keep     Keep temporary extraction folder(s)

Examples:
  Single file:
    py main.py c gif cursor.ani output.gif
    py main.py extract cursor.ani frames/
  
  Batch (folder):
    py main.py c gif cursors/ output/
    py main.py extract cursors/ extracted/
    py main.py c mp4 animations/ videos/ --keep
""")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        show_help()
        return

    cmd = sys.argv[1]

    # Handle extract command
    if cmd in ("e", "extract"):
        if len(sys.argv) < 3:
            print("Error: Missing required argument")
            print("Usage: py main.py extract <file.ani|folder> [output_dir]")
            sys.exit(1)
        
        input_path = sys.argv[2]
        
        # Parse remaining arguments (skip flags for now, get output path)
        remaining_args = sys.argv[3:]
        flags = get_flags(remaining_args)
        non_flags = get_non_flags(remaining_args)
        
        # Validate no unknown flags
        for flag in flags:
            if flag not in VALID_FLAGS:
                print(f"Error: Unknown flag '{flag}'")
                print(f"Valid flags: {', '.join(sorted(VALID_FLAGS))}")
                sys.exit(1)
        
        # Get output directory
        if non_flags:
            output_dir = non_flags[0]
            if len(non_flags) > 1:
                print(f"Error: Unexpected argument '{non_flags[1]}'")
                sys.exit(1)
        else:
            # Auto-generate output directory name
            if os.path.isdir(input_path):
                # For folder input, use folder name + "_extracted"
                folder_name = os.path.basename(os.path.normpath(input_path))
                output_dir = f"{folder_name}_extracted"
            else:
                # For file input, use file basename
                output_dir = os.path.splitext(os.path.basename(input_path))[0]
        
        if not os.path.exists(input_path):
            print(f"Error: Input path '{input_path}' does not exist")
            sys.exit(1)
        
        try:
            # Check if input is a directory (batch mode)
            if os.path.isdir(input_path):
                process_batch_extract(input_path, output_dir)
            else:
                # Single file mode
                if not input_path.lower().endswith('.ani'):
                    print(f"Error: Input file must have .ani extension")
                    sys.exit(1)
                
                output_dir = get_unique_path(output_dir)
                extract_ani(input_path, output_dir)
                print(f"Extracted → {output_dir}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Handle convert command
    if cmd in ("c", "convert"):
        if len(sys.argv) < 4:
            print("Error: Missing required arguments")
            print("Usage: py main.py convert <format> <file.ani|folder> [output_file|output_dir] [--keep|-k]")
            sys.exit(1)
        
        fmt = sys.argv[2].lower().strip(".")
        
        # Validate format
        if fmt not in SUPPORTED_FORMATS:
            print(f"Error: Invalid format '{fmt}'")
            print(f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}")
            sys.exit(1)
        
        input_path = sys.argv[3]
        
        # Parse remaining arguments
        remaining_args = sys.argv[4:]
        flags = get_flags(remaining_args)
        non_flags = get_non_flags(remaining_args)
        
        # Get output path
        if non_flags:
            output_path = non_flags[0]
            if len(non_flags) > 1:
                print(f"Error: Unexpected argument '{non_flags[1]}'")
                sys.exit(1)
        else:
            # Auto-generate output path
            if os.path.isdir(input_path):
                # For folder input, use folder name + "_output"
                folder_name = os.path.basename(os.path.normpath(input_path))
                output_path = f"{folder_name}_output"
            else:
                # For file input, use file basename + format extension
                basename = os.path.splitext(os.path.basename(input_path))[0]
                output_path = f"{basename}.{fmt}"
        
        keep = "--keep" in flags or "-k" in flags
        
        if not os.path.exists(input_path):
            print(f"Error: Input path '{input_path}' does not exist")
            sys.exit(1)
        
        try:
            # Check if input is a directory (batch mode)
            if os.path.isdir(input_path):
                process_batch_convert(input_path, output_path, fmt, keep)
            else:
                # Single file mode
                if not input_path.lower().endswith('.ani'):
                    print(f"Error: Input file must have .ani extension")
                    sys.exit(1)
                
                basename = os.path.splitext(os.path.basename(input_path))[0]
                
                if keep:
                    # For single file with --keep, put temp in output directory if it's a directory
                    if os.path.isdir(output_path):
                        temp = os.path.join(output_path, f"temp_{basename}")
                    else:
                        # If output is a file path, put temp alongside it
                        output_dir = os.path.dirname(output_path) or "."
                        temp = os.path.join(output_dir, f"temp_{basename}")
                else:
                    temp = get_unique_path(f"temp_{basename}")
                
                # Determine output file path
                if os.path.isdir(output_path):
                    out_file = os.path.join(output_path, f"{basename}.{fmt}")
                else:
                    out_file = output_path
                    # Auto-append extension if missing
                    file_ext = os.path.splitext(out_file)[1].lower().strip(".")
                    if not file_ext or file_ext != fmt:
                        out_file = f"{out_file}.{fmt}"
                
                out_file = get_unique_path(out_file)
                
                try:
                    manifest = extract_ani(input_path, temp)
                    build_animated(manifest, temp, out_file)
                    
                    print(f"Written → {out_file}")
                    if keep:
                        print(f"Temp extraction saved in: {temp}")
                except Exception as e:
                    print(f"Error: {e}")
                    sys.exit(1)
                finally:
                    # Always clean up temp folder if not keeping
                    if not keep and os.path.exists(temp):
                        shutil.rmtree(temp)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Unknown command
    print(f"Error: Unknown command '{cmd}'")
    print("Valid commands: e, extract, c, convert")
    print("Use -h or --help for usage information")
    sys.exit(1)

if __name__ == "__main__":
    main()