"""Test fixtures for the enclosure render harness.

OpenSCAD 2021.01 defaults to *ASCII* STL export, but the STL bounding-box
parser in test_enclosure.py reads the *binary* STL format. Newer OpenSCAD
releases default to binary STL, which is what the tests assume.

To keep the harness portable across OpenSCAD versions without touching the
test logic, we prepend a tiny `openscad` wrapper to PATH for the test
session. The wrapper forwards every argument unchanged but adds
`--export-format binstl` whenever the output (`-o ...`) is an .stl file and
no explicit export format was requested.
"""

import os
import stat
import textwrap

import pytest

_WRAPPER = textwrap.dedent("""\
    #!/usr/bin/env python3
    import os
    import sys

    REAL = {real!r}
    args = sys.argv[1:]

    want_stl = False
    has_fmt = "--export-format" in args
    for i, a in enumerate(args):
        if a in ("-o", "--o") and i + 1 < len(args):
            if args[i + 1].lower().endswith(".stl"):
                want_stl = True

    if want_stl and not has_fmt:
        args = args + ["--export-format", "binstl"]

    os.execv(REAL, [REAL] + args)
    """)


@pytest.fixture(scope="session", autouse=True)
def _force_binary_stl(tmp_path_factory):
    import shutil

    real = shutil.which("openscad")
    if real is None:
        yield
        return

    bindir = tmp_path_factory.mktemp("openscad_shim")
    shim = bindir / "openscad"
    shim.write_text(_WRAPPER.format(real=real))
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bindir}{os.pathsep}{old_path}"
    try:
        yield
    finally:
        os.environ["PATH"] = old_path
