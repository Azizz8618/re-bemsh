#!/usr/bin/env python3
"""Unit tests for tools/rebuild-matrix.sh.

Checks --help / --dry-run output format and the path guard. No dispak,
no emulator, no gold or image file is needed for these tests.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "rebuild-matrix.sh"


def run_script(args, env_extra=None):
    env = dict(os.environ)
    # Neutralise any inherited real image path so tests stay hermetic.
    env.pop("BESM6_PATH", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT)] + args,
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)


class TestHelpAndDryRun(unittest.TestCase):
    def test_help_exit_zero_without_dispak(self):
        r = run_script(["--help"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage: bash tools/rebuild-matrix.sh", r.stdout)
        self.assertIn("--dry-run", r.stdout)

    def test_short_help_alias(self):
        r = run_script(["-h"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)

    def test_dry_run_output_format(self):
        r = run_script(["--dry-run"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Cell            Mode Zonmod", r.stdout)
        self.assertIn("A0-base", r.stdout)
        self.assertIn("B2-trace", r.stdout)
        self.assertIn("CELLS=", r.stdout)
        cells = int(r.stdout.split("CELLS=", 1)[1].strip().splitlines()[0])
        self.assertGreaterEqual(cells, 10)

    def test_dry_run_does_not_need_dispak(self):
        # A PATH with no dispak must not break --help or --dry-run.
        env = dict(os.environ)
        env.pop("BESM6_PATH", None)
        env["PATH"] = "/nonexistent"
        r = subprocess.run(["/bin/bash", str(SCRIPT), "--dry-run"],
                           cwd=str(ROOT), env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CELLS=", r.stdout)


class TestGuard(unittest.TestCase):
    def test_refuse_real_share_in_besm6_path(self):
        r = run_script(["--dry-run"], {"BESM6_PATH": "/usr/local/share/besm6"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("REFUSE", r.stderr)

    def test_refuse_home_besm6_in_work(self):
        home = os.path.expanduser("~")
        r = run_script(["--dry-run"],
                       {"REBUILD_MATRIX_WORK": home + "/.besm6/matrix"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("REFUSE", r.stderr)

    def test_refuse_ec5061_in_work(self):
        r = run_script(["--dry-run"],
                       {"REBUILD_MATRIX_WORK": "/tmp/xxx/EC5061/copies"})
        self.assertEqual(r.returncode, 3)
        self.assertIn("REFUSE", r.stderr)

    def test_help_bypasses_guard(self):
        # --help is exempt from the guard so the usage text is always readable.
        r = run_script(["--help"], {"BESM6_PATH": "/usr/local/share/besm6"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("Usage:", r.stdout)

    def test_bad_zone_is_refused(self):
        # Stub the two tools so zone validation is reached without dispak.
        with tempfile.TemporaryDirectory(prefix="matrix-stub-") as d:
            for name in ("dispak", "python3"):
                p = Path(d) / name
                p.write_text("#!/bin/sh\nexit 0\n")
                p.chmod(0o755)
            env = dict(os.environ)
            env.pop("BESM6_PATH", None)
            env["PATH"] = d + os.pathsep + env.get("PATH", "")
            r = subprocess.run(["/bin/bash", str(SCRIPT), "not-octal-999"],
                               cwd=str(ROOT), env=env,
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("octal", r.stderr)


if __name__ == "__main__":
    unittest.main()
