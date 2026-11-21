import fcntl
import hashlib
import json
import tempfile
from pathlib import Path

from .agents import agent
from .core import Stop, gh, home, run, save
from .workflow import checked, git, pages, transact


def select(entries):
    for index, (label, _) in enumerate(entries, 1):
        print(f"{index}. {label}")
    if not entries:
        raise Stop("No unfinished local runs or open authored PRs were found.")
    choice = int(input("Select a run or PR: "))
    if not 1 <= choice <= len(entries):
        raise Stop("Selection outside the list.")
    return entries[choice - 1][1]


def continue_work(prefs):
    entries = []
    for path in sorted((home() / "runs").glob("*/*/*/state.json")):
        state = json.loads(path.read_text())
        if not state.get("pr"):
            entries.append((f"Resume {state['issue']}", ("issue", state["issue"])))
    prs = gh("search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
             "--sort", "updated", "--visibility", "public", "--json", "url,title")
    entries.extend((f"{p['title']}  {p['url']}", ("pr", p["url"])) for p in prs)
    kind, url = select(entries)
    if kind == "issue":
        return transact(url, prefs)
    return follow_pr(url)


def review_requests(repo, number):
    endpoint = f"repos/{repo}"
    comments = pages(f"{endpoint}/issues/{number}/comments")
    reviews = pages(f"{endpoint}/pulls/{number}/reviews")
    inline = pages(f"{endpoint}/pulls/{number}/comments")
    if inline:
        # A REST inline comment can outlive the review thread that was resolved.
        owner, name = repo.split("/")
        query = """query($owner:String!, $name:String!, $number:Int!, $endCursor:String) {
          repository(owner:$owner,name:$name) { pullRequest(number:$number) {
            reviewThreads(first:100,after:$endCursor) {
              nodes { isResolved isOutdated comments(first:1) { nodes { databaseId } } }
              pageInfo { hasNextPage endCursor }
            }
          } }
        }"""
        batches = gh("api", "graphql", "--paginate", "--slurp", "-f", f"query={query}",
                     "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"number={number}")
        active = set()
        for batch in batches:
            threads = batch["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
            for thread in threads:
                if not thread["isResolved"] and not thread["isOutdated"]:
                    active.update(c["databaseId"] for c in thread["comments"]["nodes"])
        inline = [row for row in inline if row.get("in_reply_to_id", row["id"]) in active]
    records = []
    for row in comments + reviews + inline:
        if row["author_association"] not in {"OWNER", "MEMBER", "COLLABORATOR"}:
            continue
        if row.get("state") in {"DISMISSED", "APPROVED"}:
            continue
        if row.get("body"):
            records.append(dict(url=row["html_url"], body=row["body"], path=row.get("path"),
                                author=row["user"]["login"], state=row.get("state")))
    return records


def follow_pr(url):
    parts = url.split("/")
    repo, number = "/".join(parts[3:5]), int(parts[6])
    root = home() / "reviews" / repo.lower() / str(number)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop(f"Another process is handling {url}.")
        update_pr(root, repo, number, url)


def update_pr(root, repo, number, url):
    endpoint = f"repos/{repo}/pulls/{number}"
    pr = gh("api", endpoint)
    login = run("gh", "api", "user", "--jq", ".login")
    head = pr["head"]
    if (pr["state"] != "open" or pr["user"]["login"] != login or not head["repo"]
            or head["repo"]["owner"]["login"] != login
            or head["repo"]["default_branch"] == head["ref"]):
        raise Stop(f"Follow-up requires an open authored PR on your own topic branch: {url}")
    feedback = review_requests(repo, number)
    if not feedback:
        raise Stop(f"No maintainer review feedback found on {url}")
    fingerprint = hashlib.sha256(json.dumps(feedback, sort_keys=True).encode()).hexdigest()
    path = root / "state.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    checkout = root / "checkout"
    if state.get("feedback") == fingerprint and state.get("commit") == head["sha"]:
        print(f"Reviewed update already published: {url} at {head['sha']}")
        return
    if state.get("feedback") != fingerprint or state.get("parent") != head["sha"]:
        state = dict(pr=url, branch=head["ref"], parent=head["sha"], feedback=fingerprint)
        save(path, state)
    remote = head["repo"]["clone_url"]
    if not checkout.exists():
        git(root, "clone", "--no-checkout", remote, str(checkout))
    git(checkout, "fetch", remote, f"refs/heads/{head['ref']}")
    if git(checkout, "rev-parse", "FETCH_HEAD") != head["sha"]:
        raise Stop("PR head advanced while fetching. Resume with the new head.")
    context = dict(pr=url, title=pr["title"], description=pr["body"], feedback=feedback,
                   parent=head["sha"], diff=run("gh", "pr", "diff", url))
    if not state.get("commit"):
        # Keep interrupted work available and start the new attempt from the remote snapshot.
        attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=root))
        git(checkout, "worktree", "add", "--detach", str(attempt), head["sha"])
        report = agent("implementer", attempt,
                       "Inspect the existing PR and maintainer feedback. Stop if feedback is ambiguous, "
                       "superseded, already addressed, or has no actionable request. Otherwise address "
                       "only outstanding changes following project rules. Run relevant tests yourself.",
                       context, {"tests": "string"})
        checked(report, ["tests"])
        git(attempt, "add", "-A")
        if not git(attempt, "diff", "--cached", "--name-only"):
            raise Stop("No outstanding code change. " + report["reason"])
        git(attempt, "commit", "-m", "Address PR review feedback")
        state.update(commit=git(attempt, "rev-parse", "HEAD"), implementation=report,
                     checkout=str(attempt))
        save(path, state)
    with tempfile.TemporaryDirectory() as tmp:
        review = Path(tmp) / "review"
        git(root, "clone", "--no-local", state["checkout"], str(review))
        git(review, "switch", "--detach", state["commit"])
        context["commit"] = state["commit"]
        report = agent("reviewer", review,
                       "Review parent..commit against the maintainer requests and project rules. "
                       "Rerun relevant tests. Approve only a clean, scoped and passing update.",
                       context, {"tests": "string"})
        checked(report, ["tests"])
        if git(review, "diff", "HEAD", "--name-only") or git(review, "rev-parse", "HEAD") != state["commit"]:
            raise Stop("Reviewer modified the reviewed source.")
    state["review"] = report
    save(path, state)
    current = gh("api", endpoint)
    if (current["state"] != "open" or current["head"]["sha"] != head["sha"]
            or review_requests(repo, number) != feedback):
        raise Stop("PR changed during review. Resume with the new context.")
    git(Path(state["checkout"]), "push", remote, f"{state['commit']}:refs/heads/{head['ref']}")
    print(f"Updated {url} to reviewed commit {state['commit']}")
