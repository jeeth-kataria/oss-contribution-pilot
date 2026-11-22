# Reproduce the recorded deadline trace

Start in a throwaway clone of Firecrawl containing refs/pull/5944/head. The historical implementation commit is 638b82db7744ab5cbc918a82919ff119bf25be71 and the merge base used in the replay is 41b36dfd28ad69df7da221d1d51f3d5fb4838be3. The demo adds an instrumented test to the historical fix in a local commit. This accounts for the fix SHA in the report.

Check out the implementation commit. Copy the adjacent test_wait_trace.py into apps/python-sdk, then commit just that test in the throwaway clone. Activate an environment with the Firecrawl SDK test dependencies and OSS Contribution Pilot installed. From apps/python-sdk run:

```sh
oss-pilot prove --base 41b36df --test test_wait_trace.py::test_deadline --output deadline.html
```

Each revision prints a POLL_TRACE line with fake-clock request, sleep, and outcome events. The demo's events.json contains those two arrays. At the base the polling function returned a completed job after ten simulated seconds. At the fix it raised CrawlJobTimeoutError at one simulated second.
