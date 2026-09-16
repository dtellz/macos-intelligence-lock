#!/usr/bin/env python3
"""Sandboxed regression tests for apple-pcc-block.sh (Python 3.8+).

Usage:
    python3 test_apple_pcc_block.py
    python3 test_apple_pcc_block.py --script path/to/apple-pcc-block.sh

No administrator privileges, real hosts-file writes, or DNS-cache changes.
A temporary COPY of the script is instrumented to use fixture paths, bypass
sudo, and replace macOS resolver/cache utilities with a no-op. Tests validate
shell behavior, not network blocking or compatibility with macOS services.
"""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).resolve().with_name("apple-pcc-block.sh")
BASH = shutil.which("bash")
BEGIN = "# >>> APPLE PRIVATE CLOUD COMPUTE BLOCK >>>"
END = "# <<< APPLE PRIVATE CLOUD COMPUTE BLOCK <<<"
BASE_HOSTS = (
    "# Existing entries must survive\n"
    "127.0.0.1\tlocalhost\n"
    "::1\tlocalhost\n"
    "192.0.2.10\tkeep-this-entry.test\n"
)


def replace_exact(source: str, old: str, new: str, count: int = 1) -> str:
    """Fail closed if the script no longer matches the sandbox assumptions."""
    actual = source.count(old)
    if actual != count:
        raise AssertionError(
            f"Cannot safely instrument script: expected {count} occurrences "
            f"of {old!r}, found {actual}"
        )
    return source.replace(old, new)


class ScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        if BASH is None:
            self.skipTest("Bash is required")
        scratch = tempfile.TemporaryDirectory(prefix="pcc-block-test-")
        self.addCleanup(scratch.cleanup)
        # These characters also test that the trap safely quotes its pathname.
        root = Path(scratch.name) / "sandbox 'quotes' $HOME [brackets]"
        root.mkdir()
        self.hosts = root / "hosts"
        self.hosts.write_text(BASE_HOSTS, encoding="utf-8")
        self.temp_files = root / "temporary files"
        self.temp_files.mkdir()
        self.fixture_script = root / "apple-pcc-block.sh"
        noop = root / "noop"
        noop.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        noop.chmod(0o700)

        source = SCRIPT_PATH.read_text(encoding="utf-8")
        source = replace_exact(
            source, 'HOSTS_FILE="/etc/hosts"',
            "HOSTS_FILE=" + shlex.quote(str(self.hosts)),
        )
        source = replace_exact(
            source, 'exec sudo -- "$0" "$@"',
            "return 0  # TEST COPY ONLY: never invoke sudo",
        )
        source = replace_exact(
            source, "mktemp /tmp/apple-pcc-hosts.XXXXXX",
            "mktemp " + shlex.quote(str(self.temp_files / "apple-pcc-hosts.XXXXXX")),
            count=2,
        )
        source = replace_exact(
            source, "/usr/bin/dscacheutil", shlex.quote(str(noop)), count=2,
        )
        source = replace_exact(
            source, "/usr/bin/killall", shlex.quote(str(noop)),
        )
        self.fixture_script.write_text(source, encoding="utf-8")

    def run_script(self, command: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        # Do not inherit startup scripts or a variable that could mask the bug.
        for name in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "tmp"):
            env.pop(name, None)
        return subprocess.run(
            [BASH, str(self.fixture_script), command],
            capture_output=True, text=True, timeout=10, env=env,
        )

    def assert_success(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(
            result.returncode, 0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertNotIn("unbound variable", result.stderr)

    def assert_no_temporary_files(self) -> None:
        self.assertEqual(list(self.temp_files.iterdir()), [])

    def test_shell_syntax(self) -> None:
        result = subprocess.run(
            [BASH, "-n", str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=10,
        )
        self.assert_success(result)

    def test_show_does_not_modify_hosts(self) -> None:
        result = self.run_script("show")
        self.assert_success(result)
        self.assertIn(BEGIN, result.stdout)
        self.assertIn(END, result.stdout)
        self.assertEqual(self.hosts.read_text(), BASE_HOSTS)
        self.assert_no_temporary_files()

    def test_status_without_block(self) -> None:
        result = self.run_script("status")
        self.assert_success(result)
        self.assertIn("Managed block: NOT INSTALLED", result.stdout)
        self.assertEqual(self.hosts.read_text(), BASE_HOSTS)
        self.assert_no_temporary_files()

    def test_enable_cleans_up_after_function_returns(self) -> None:
        result = self.run_script("enable")
        self.assert_success(result)
        current = self.hosts.read_text()
        self.assertTrue(current.startswith(BASE_HOSTS))
        self.assertEqual(current.count(BEGIN), 1)
        self.assertEqual(current.count(END), 1)
        self.assertIn("Managed block: INSTALLED", result.stdout)
        backups = list(self.hosts.parent.glob("hosts.before-pcc-block.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), BASE_HOSTS)
        self.assert_no_temporary_files()

    def test_disable_cleans_up_and_preserves_surrounding_entries(self) -> None:
        block_result = self.run_script("show")
        self.assert_success(block_result)
        footer = "192.0.2.20\tentry-after-block.test\n"
        self.hosts.write_text(BASE_HOSTS + block_result.stdout + footer)
        result = self.run_script("disable")
        self.assert_success(result)
        self.assertIn("PCC hostname block disabled.", result.stdout)
        self.assertEqual(self.hosts.read_text(), BASE_HOSTS + footer)
        self.assert_no_temporary_files()

    def test_noop_disable_cleans_up_on_early_exit(self) -> None:
        result = self.run_script("disable")
        self.assert_success(result)
        self.assertIn("Nothing to do.", result.stdout)
        self.assertEqual(self.hosts.read_text(), BASE_HOSTS)
        self.assertEqual(list(self.hosts.parent.glob("hosts.before-pcc-block.*")), [])
        self.assert_no_temporary_files()

    def test_repeated_enable_does_not_duplicate_block(self) -> None:
        for _ in range(2):
            self.assert_success(self.run_script("enable"))
            self.assert_no_temporary_files()
        current = self.hosts.read_text()
        self.assertEqual(current.count(BEGIN), 1)
        self.assertEqual(current.count(END), 1)
        self.assertTrue(current.startswith(BASE_HOSTS))

    def test_enable_disable_round_trip(self) -> None:
        self.assert_success(self.run_script("enable"))
        self.assert_no_temporary_files()
        self.assert_success(self.run_script("disable"))
        self.assert_no_temporary_files()
        # Existing script leaves a separator blank line; ignore it here.
        self.assertEqual(self.hosts.read_text().rstrip(), BASE_HOSTS.rstrip())
        result = self.run_script("status")
        self.assert_success(result)
        self.assertIn("Managed block: NOT INSTALLED", result.stdout)

    def test_backup_failure_keeps_status_and_cleans_up(self) -> None:
        source = self.fixture_script.read_text()
        source = replace_exact(
            source, "set -euo pipefail",
            "set -euo pipefail\ncp() { return 73; }  # Simulated backup failure",
        )
        self.fixture_script.write_text(source)
        result = self.run_script("enable")
        self.assertEqual(result.returncode, 73, msg=result.stderr)
        self.assertNotIn("unbound variable", result.stderr)
        self.assertEqual(self.hosts.read_text(), BASE_HOSTS)
        self.assert_no_temporary_files()

    def test_unknown_command_preserves_usage_exit_status(self) -> None:
        result = self.run_script("invalid-command")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stdout)
        self.assertEqual(self.hosts.read_text(), BASE_HOSTS)
        self.assert_no_temporary_files()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=SCRIPT_PATH)
    args = parser.parse_args()
    SCRIPT_PATH = args.script.resolve()
    if not SCRIPT_PATH.is_file():
        parser.error(f"Script not found: {SCRIPT_PATH}")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ScriptTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
