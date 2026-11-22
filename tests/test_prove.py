import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest

from oss_pilot.prove import git, prove, verdict


class RegressionProof(unittest.TestCase):
    def test_real_worktrees(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            previous = Path.cwd()
            self.addCleanup(os.chdir, previous)
            os.chdir(root)
            git(root, "init", "-q")
            (root / "calc.py").write_text("value = 1\n")
            git(root, "add", ".")
            self.commit(root)
            base = git(root, "rev-parse", "HEAD")
            (root / "calc.py").write_text("value = 2\n")
            (root / "test_calc.py").write_text(
                "import pytest, time\nfrom calc import value\n"
                "def test_fix(): assert value == 2\n"
                "def test_both(): assert value > 0\n"
                "def test_head(): assert value == 1\n"
                "def test_setup(missing_fixture): pass\n"
                "def test_skip(): pytest.skip()\n"
                "def test_timeout(): time.sleep(5)\n")
            git(root, "add", ".")
            self.commit(root)
            (root / "calc.py").write_text("uncommitted = True\n")
            initial = git(root, "status", "--porcelain")
            with tempfile.TemporaryDirectory() as reports:
                out = Path(reports) / "report.html"
                for name, expected in [
                    ("fix", "Reproduced before, passed after"),
                    ("both", "This test did not distinguish the fix"),
                    ("head", "Failing on the fix"), ("setup", "Inconclusive"),
                    ("skip", "Inconclusive"), ("timeout", "Inconclusive")]:
                    with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()):
                        code = prove(["--base", base, "--test", f"test_calc.py::test_{name}",
                                      "--timeout", "1" if name == "timeout" else "30",
                                      "--output", str(out)])
                        self.assertEqual(code, int(name != "fix"))
                        self.assertIn(f"<title>{expected}</title>", out.read_text())
            self.assertEqual(git(root, "status", "--porcelain"), initial)
            self.assertEqual(len(git(root, "worktree", "list").splitlines()), 1)

    @staticmethod
    def commit(root):
        git(root, "-c", "user.name=Fixture", "-c", "user.email=test@example.org",
            "commit", "-qm", "Fixture revision")

    def test_mismatched_selection(self):
        def run(node):
            return dict(code=0, rows=[dict(node=node, outcome="passed", phase="call", xfail=False)])
        self.assertEqual(verdict(run("a"), run("b"))[0], "Inconclusive")
