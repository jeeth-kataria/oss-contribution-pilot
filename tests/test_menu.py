import unittest
from unittest.mock import patch

from oss_pilot.cli import menu


class Menu(unittest.TestCase):
    @patch("oss_pilot.cli.transact")
    @patch("oss_pilot.cli.shortlist", return_value=[{"url": "first"}, {"url": "second"}])
    @patch("oss_pilot.cli.preferences", return_value={"paid_only": True})
    @patch("builtins.input", return_value="2")
    def test_find_and_publish_starts_exactly_one_issue(self, answer, prefs, shortlist, transact):
        menu()
        transact.assert_called_once_with("first", prefs.return_value)
