import os
import shutil
import struct
import subprocess
import tempfile

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("openscad") is None, reason="openscad CLI not installed"
)

SCAD = os.path.join(os.path.dirname(__file__), "..", "enclosure", "ld2460_case.scad")
PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "..", "enclosure", "preview")


def render_stl(part, defs=None):
    """Render a part to STL. Returns (CompletedProcess, stl_path)."""
    out = tempfile.NamedTemporaryFile(suffix=".stl", delete=False).name
    cmd = ["openscad", "-o", out, "-D", f'part="{part}"']
    for k, v in (defs or {}).items():
        cmd += ["-D", f"{k}={v}"]
    cmd += ["--hardwarnings", SCAD]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc, out


def render_png(part, name):
    """Render a preview PNG into enclosure/preview/ for human inspection."""
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    out = os.path.join(PREVIEW_DIR, name)
    subprocess.run(
        ["openscad", "-o", out, "-D", f'part="{part}"', "--imgsize=900,700", SCAD],
        capture_output=True,
        text=True,
    )
    return out


def stl_bbox(path):
    """Return (dx, dy, dz) bounding-box size of a binary STL."""
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 80)[0]
    xs, ys, zs = [], [], []
    off = 84
    for _ in range(n):
        base = off + 12  # skip the 3-float normal
        for v in range(3):
            x, y, z = struct.unpack_from("<fff", data, base + v * 12)
            xs.append(x)
            ys.append(y)
            zs.append(z)
        off += 50
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def stl_z_min(path):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 80)[0]
    zmin = float("inf")
    off = 84
    for _ in range(n):
        base = off + 12
        for v in range(3):
            _, _, z = struct.unpack_from("<fff", data, base + v * 12)
            zmin = min(zmin, z)
        off += 50
    return zmin


def test_shell_renders_and_outer_size_is_sane():
    proc, stl = render_stl("shell")
    assert proc.returncode == 0, proc.stderr
    dx, dy, dz = stl_bbox(stl)
    # Outer width ≈ board width (32) + 2*fit_clear (0.8) + 2*wall (4) ≈ 36.8
    assert 35.0 <= dx <= 39.0, f"width {dx}"
    # Tall enough to hold the 49.5 mm board plus the foot
    assert dz >= 50.0, f"height {dz}"
    render_png("all", "assembly.png")
