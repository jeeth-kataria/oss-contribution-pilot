import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oss_pilot.core import Stop
from oss_pilot.workflow import checked, evidence, issue_id, publish


class Gates(unittest.TestCase):
    def test_issue_urls(self):
        self.assertEqual(issue_id("https://github.com/org/project/issues/13"), ("org/project", 13))
        for url in ["https://github.com/../project/issues/1", "https://github.com/org/r/pull/1"]:
            with self.assertRaises(Stop):
                issue_id(url)

    @patch("oss_pilot.workflow.gh")
    def test_competing_pr(self, gh):
        gh.side_effect = [dict(state="open", locked=False, assignees=[], html_url="issue"), [[]],
                          [[dict(source=dict(issue=dict(state="open", pull_request=True, html_url="pr")))]]]
        with self.assertRaisesRegex(Stop, "references this issue: pr"):
            evidence("project/repo", 1, "me")

    def test_fail_closed(self):
        for report in [dict(proceed=False, tests="passed", reason="duplicate proposal"),
                       dict(proceed=True, tests="", reason="missing evidence")]:
            with self.assertRaises(Stop):
                checked(report, ["tests"])

    @patch("oss_pilot.workflow.run", return_value="https://github.com/me/repo/pull/2")
    @patch("oss_pilot.workflow.git")
    def test_publishes_reviewed_sha_and_evidence(self, git, run):
        state = dict(repo="me/repo", login="me", branch="topic", base="main", commit="abc",
                     issue="issue", implementation=dict(reason="summary", reproduction="before", tests="after"),
                     review=dict(tests="independent run"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publish(root, root / "state.json", state, root, dict(title="Fix"))
            git.assert_called_once_with(root, "push", "https://github.com/me/repo.git", "abc:refs/heads/topic")
            self.assertIn("independent run", (root / "pr-body.md").read_text())
            self.assertEqual(state["pr"], run.return_value)
