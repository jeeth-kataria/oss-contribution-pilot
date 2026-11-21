import unittest
from unittest.mock import patch

from oss_pilot.core import discover


class Discovery(unittest.TestCase):
    @patch("oss_pilot.core.gh")
    def test_deduplicate_and_filter(self, gh):
        issue = dict(url="u", title="$20 bug", updatedAt="2026", labels=[], isLocked=False)
        gh.return_value = [issue, dict(issue, url="v", title="Bug"),
                           dict(issue, url="w", isLocked=True)]
        prefs = dict(topics=["inference", "agents"], languages=["Python"], paid_only=True)
        self.assertEqual(discover(prefs), [issue])

    @patch("oss_pilot.core.gh")
    def test_paid_only_matches_paid_as_a_standalone_word(self, gh):
        paid = dict(url="u", title="[Paid] Fix bug", updatedAt="2026", labels=[], isLocked=False)
        unpaid = dict(paid, url="v", title="Unpaid bug fix")
        paid_label = dict(paid, url="x", title="Fix bug", labels=[{"name": "paid"}])
        unpaid_label = dict(paid_label, url="y", labels=[{"name": "unpaid"}])
        gh.return_value = [paid, unpaid, paid_label, unpaid_label]
        prefs = dict(topics=["inference"], languages=["Python"], paid_only=True)
        self.assertEqual(discover(prefs), [paid, paid_label])
