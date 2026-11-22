"""Replay two independent Codex reviews against local candidate patches."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from oss_pilot import workflow as w

real_agent = w.agent

def scenario(candidate):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "source"
        source.mkdir()
        w.git(source, "init", "-b", "main")
        (source / "calc.py").write_text("def twice(n): return n + 1\n")
        (source / ".gitignore").write_text("__pycache__/\n")
        w.git(source, "add", ".")
        w.git(source, "commit", "-m", "Seed arithmetic bug")
        git = w.git
        real_run = w.run
        def local_git(cwd, *args):
            if "push" in args:
                raise AssertionError("Unexpected push")
            return git(cwd, *(str(source) if str(a).startswith("https://") else a for a in args))

        def agent(role, cwd, task, context, fields):
            if role == "implementer":
                (cwd / "calc.py").write_text(f"def twice(n): return {candidate}\n")
                (cwd / "test_calc.py").write_text("import unittest\nfrom calc import twice\nclass TestCalc(unittest.TestCase):\n    def test_integer(self): self.assertEqual(twice(3), 6)\n")
                subprocess.run([sys.executable, "-B", "-m", "unittest"], cwd=cwd, check=True)
                return dict(proceed=True, reason="Updated doubling", reproduction="Old twice(3) returned 4", tests="Integer unittest passed")
            if role == "reviewer":
                return real_agent(role, cwd, task, context, fields)
            return dict(proceed=True, reason="Local fixture", reward_confirmed=False)

        def preview(root, path, state, checkout, context):
            print("Publication intercepted. Reviewed diff:")
            print(git(checkout, "diff", state["base_commit"], state["commit"]))

        with patch.dict(os.environ, OSS_PILOT_HOME=tmp), patch.object(w, "git", local_git), patch.object(w, "gh", side_effect=lambda *a: dict(isArchived=False,isPrivate=False,defaultBranchRef=dict(name="main")) if a[0]=="repo" else []), patch.object(w, "run", side_effect=lambda *a, **kw: real_run(*a, **kw) if a[0]=="git" else "local"), patch.object(w, "evidence", return_value=dict(title="Correct doubling", body="twice(3) returns 4. Double the numeric input, preserving fractional results.", state="open", locked=False, assignees=[], comments=[], open_prs=[], labels=[], linked_open_prs=[])), patch.object(w, "agent", agent), patch.object(w, "publish", preview):
            url = "https://github.com/local/example/issues/1"
            blocked = False
            try:
                w.transact(url, dict(paid_only=False))
            except w.Stop:
                blocked = True
            state_path = next(root.glob("runs/*/*/*/state.json"))
            state = json.loads(state_path.read_text())
            report = state["review"]
            diff = git(state_path.parent / "checkout", "diff", state["base_commit"], state["commit"])
            evidence = dict(report=report, diff=diff, blocked=blocked)
            with tempfile.NamedTemporaryFile(mode="w", prefix="review-result-", suffix=".json", delete=False) as artifact:
                json.dump(evidence, artifact, indent=2)
            print(artifact.name, report, flush=True)
            return report["proceed"] and not blocked

if __name__ == "__main__":
    outcomes = [scenario(expr) for expr in ("int(n * 2)", "n * 2")]
    if outcomes != [False, True]:
        sys.exit("Replay verdicts differed from the recorded experiment.")
