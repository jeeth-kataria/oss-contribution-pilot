"""Run in Firecrawl's apps/python-sdk at the revisions linked in the demo."""
import json
from unittest.mock import Mock

from firecrawl import Firecrawl
from firecrawl.v2.methods import crawl
from firecrawl.v2.utils import CrawlJobTimeoutError


def test_deadline(monkeypatch):
    events = []
    now = 0

    def sleep(duration):
        nonlocal now
        events.append(dict(kind="sleep", at=now, duration=duration))
        now += duration

    def get(*args, **kwargs):
        status = "completed" if events else "scraping"
        events.append(dict(kind="request", at=now))
        response = Mock(ok=True, status_code=200)
        response.json.return_value = dict(success=True, status=status, data=[], total=1,
                                          completed=int(status == "completed"), creditsUsed=0)
        return response

    client = Firecrawl(api_key="fc-test")
    monkeypatch.setattr(crawl, "time", Mock(monotonic=lambda: now, sleep=sleep))
    monkeypatch.setattr(client._v2_client.http_client, "get", get)
    try:
        client.wait_crawl("test-job", timeout=1, poll_interval=10, request_timeout=3)
        outcome = "completed"
    except CrawlJobTimeoutError:
        outcome = "timeout"
    events.append(dict(kind=outcome, at=now))
    print("POLL_TRACE", json.dumps(events))
    assert (outcome, now, sum(e["kind"] == "request" for e in events)) == ("timeout", 1, 1)
