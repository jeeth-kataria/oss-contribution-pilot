"""Loaded only by the isolated pytest subprocess."""
import json
import os


def pytest_runtest_logreport(report):
    if report.when == "call" or report.failed or report.skipped:
        crash = getattr(report.longrepr, "reprcrash", None)
        with open(os.environ["OSS_PILOT_OBSERVATIONS"], "a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(node=report.nodeid, phase=report.when,
                                         outcome=report.outcome, xfail=hasattr(report, "wasxfail"),
                                         error=getattr(crash, "message", ""))) + "\n")
