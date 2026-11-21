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
