import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from oss_pilot.core import save
from oss_pilot.workflow import work
from oss_pilot.follow import select, update_pr


class Restart(unittest.TestCase):
    @patch("oss_pilot.workflow.agent", side_effect=AssertionError("unexpected agent"))
    @patch("oss_pilot.workflow.gh")
    @patch("oss_pilot.workflow.run", return_value="me")
    def test_restart_after_pr_creation(self, run, gh, agent):
        gh.side_effect = [dict(isArchived=False, isPrivate=False, defaultBranchRef=dict(name="main")),
                          [dict(state="open", user=dict(login="me"), html_url="pr")]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "state.json", dict(login="me", branch="topic", base="main", commit="sha"))
            work(root, "me/repo", 1, "issue", {})
            self.assertEqual(json.loads((root / "state.json").read_text())["pr"], "pr")

    @patch("oss_pilot.follow.agent", side_effect=AssertionError("unexpected agent"))
    @patch("oss_pilot.follow.review_requests", return_value=[dict(body="cover labels")])
    @patch("oss_pilot.follow.gh")
    @patch("oss_pilot.follow.run", return_value="me")
    def test_restart_after_followup_push(self, run, gh, feedback, agent):
        import hashlib
        head = dict(sha="reviewed", ref="topic", repo=dict(owner=dict(login="me"), default_branch="main"))
        gh.return_value = dict(head=head, state="open", user=dict(login="me"))
        fingerprint = hashlib.sha256(json.dumps(feedback.return_value, sort_keys=True).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "state.json", dict(commit="reviewed", feedback=fingerprint))
            update_pr(root, "me/repo", 2, "pr")

    @patch("builtins.input", return_value="0")
    def test_no_negative_menu_index(self, _):
        from oss_pilot.core import Stop
        with self.assertRaises(Stop):
            select([("example", "pr")])
