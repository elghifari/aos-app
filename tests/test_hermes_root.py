import unittest
from pathlib import Path
from unittest.mock import patch

import aos


class HermesRootTests(unittest.TestCase):
    def root(self, env, platform, home=Path("/home/el")):
        with patch.dict("os.environ", env, clear=True), \
                patch("aos.sys.platform", platform), \
                patch("aos.Path.home", return_value=home):
            return aos.hermes_root()

    def test_explicit_root_wins_on_any_platform(self):
        for platform in ("win32", "linux", "darwin"):
            with self.subTest(platform=platform):
                self.assertEqual(
                    self.root({"AOS_HERMES_ROOT": "/srv/hermes"}, platform),
                    Path("/srv/hermes"))

    def test_hermes_home_is_ignored(self):
        self.assertEqual(
            self.root({"HERMES_HOME": "/home/el/.hermes/profiles/pod-p1-growth"},
                      "linux"),
            Path("/home/el/.hermes"))

    def test_windows_default_is_localappdata(self):
        self.assertEqual(
            self.root({"LOCALAPPDATA": r"C:\Users\el\AppData\Local"}, "win32"),
            Path(r"C:\Users\el\AppData\Local") / "hermes")

    def test_windows_without_localappdata_falls_back_to_home(self):
        self.assertEqual(
            self.root({}, "win32", home=Path(r"C:\Users\el")),
            Path(r"C:\Users\el") / "AppData" / "Local" / "hermes")

    def test_linux_and_macos_default_is_dot_hermes(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                self.assertEqual(self.root({}, platform), Path("/home/el/.hermes"))

    def test_blank_override_uses_the_default(self):
        self.assertEqual(self.root({"AOS_HERMES_ROOT": "  "}, "linux"),
                         Path("/home/el/.hermes"))

    def test_override_expands_home(self):
        home = {"HOME": "/home/el", "USERPROFILE": "/home/el"}
        self.assertEqual(
            self.root({"AOS_HERMES_ROOT": "~/hermes", **home}, "linux"),
            Path("/home/el") / "hermes")
