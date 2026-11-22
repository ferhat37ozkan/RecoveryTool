"""Cleanup tools: deletion stays inside its folder and never follows links or junctions.

    python tests\\test_cleanup.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise.tools import junk  # noqa: E402


def test_junction_is_not_followed():
    base = tempfile.mkdtemp(prefix="bw-clean-")
    try:
        root, outside = os.path.join(base, "root"), os.path.join(base, "outside")
        os.makedirs(os.path.join(root, "sub"))
        os.makedirs(os.path.join(outside, "empty"))
        for path in (os.path.join(root, "a.tmp"), os.path.join(root, "sub", "b.tmp"), os.path.join(outside, "keep.txt")):
            with open(path, "w") as f:
                f.write("x")
        link = os.path.join(root, "link")
        subprocess.run(["cmd", "/c", "mklink", "/J", link, outside], capture_output=True, check=True)
        seen = sorted(os.path.relpath(p, root) for p, _ in junk.walk_files(root))
        assert seen == ["a.tmp", os.path.join("sub", "b.tmp")], seen
        freed, skipped = junk.clean([{"key": "test", "paths": [root], "size": 0}], lambda k: None)
        assert freed == 2 and skipped == 0, (freed, skipped)
        assert os.listdir(root) == ["link"], os.listdir(root)                  # the junction itself stays
        assert sorted(os.listdir(outside)) == ["empty", "keep.txt"], os.listdir(outside)
    finally:
        link = os.path.join(base, "root", "link")
        if os.path.isdir(link):
            os.rmdir(link)                                                    # remove the junction, not its target
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    test_junction_is_not_followed()
    print("cleanup tests passed")
