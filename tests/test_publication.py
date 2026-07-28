import hashlib
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON_ID = "plugin.video.plexkodiconnect.tvshows"
EXPECTED_MEMBERS = {f"{ADDON_ID}/{name}" for name in ("addon.xml", "changelog.txt", "default.py", "icon.png")}
PACKAGE_SHA = "e0c07e492599658d2ecaf0a188de09b2abdb6375"
NOTIFIER_SHA = "a1730e889acf1816fd6d8c856c10b9ce97747829"


class PublicationContractTests(unittest.TestCase):
    def build(self, output):
        subprocess.run(
            ["python3", "scripts/build_release.py", "--source", ".", "--output", str(output), "--expected-version", "5.0.1"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_release_archive_is_exact_and_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.zip"
            second = Path(directory) / "b.zip"
            self.build(first)
            self.build(second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), EXPECTED_MEMBERS)
                self.assertEqual(len(archive.namelist()), len(EXPECTED_MEMBERS))

    def test_release_builder_rejects_symlinked_runtime_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            for name in ("addon.xml", "changelog.txt", "default.py", "icon.png"):
                (source / name).write_bytes((ROOT / name).read_bytes())
            (source / "icon.png").unlink()
            (source / "icon.png").symlink_to(ROOT / "icon.png")
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/build_release.py"), "--source", str(source), "--output", str(Path(directory) / "bad.zip"), "--expected-version", "5.0.1"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", (result.stdout + result.stderr).lower())

    def test_workflows_pin_current_target_tooling_and_actions(self):
        validations = (ROOT / ".github/workflows/addon-validations.yml").read_text()
        notifier = (ROOT / ".github/workflows/notify-repository.yml").read_text()
        release = (ROOT / ".github/workflows/make-release.yml").read_text()
        self.assertIn(f"reusable-addon-package.yml@{PACKAGE_SHA}", validations)
        self.assertIn(f"reusable-notify-repository.yml@{NOTIFIER_SHA}", notifier)
        self.assertIn("workflow_dispatch:", validations)
        self.assertIn("workflow_run:", notifier)
        self.assertIn("workflow_dispatch", notifier)
        self.assertIn("validation_event: ${{ github.event.workflow_run.event }}", notifier)
        self.assertIn(
            "validation_workflow_path: .github/workflows/addon-validations.yml",
            notifier,
        )
        self.assertNotIn("addon-validations.yml@develop", notifier)
        self.assertIn("head_branch == 'develop'", notifier)
        self.assertNotIn("addon-updated", notifier)
        combined = validations + notifier + release
        self.assertNotIn("actions/checkout@v", combined)
        self.assertNotIn("actions/setup-python@v", combined)
        self.assertNotIn("actions/download-artifact@v", combined)
        self.assertNotIn("softprops/action-gh-release@", combined)
        self.assertIn("workflow_dispatch:", release)
        self.assertNotIn("push:\n    branches: [main]", release)
        self.assertIn("actions/runs/{run_id}", release)
        self.assertIn("validation-evidence", release)
        self.assertIn("addon-package", release)
        self.assertIn("validation evidence commit mismatch", release)
        self.assertIn("validation evidence archive hash mismatch", release)
        self.assertNotIn("scripts/build_release.py", release)
        self.assertIn('ref="refs/tags/$tag"', release)
        self.assertIn("git/refs", release)
        self.assertIn("--verify-tag", release)
        self.assertIn("concurrency:", release)

    def test_metadata_is_version_5_0_1(self):
        addon = (ROOT / "addon.xml").read_text()
        changelog = (ROOT / "changelog.txt").read_text()
        self.assertIn('version="5.0.1"', addon)
        self.assertTrue(changelog.startswith("version 5.0.1\n"))


if __name__ == "__main__":
    unittest.main()
