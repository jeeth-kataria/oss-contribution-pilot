import fcntl
import json
import re
import tempfile
from pathlib import Path

from .agents import agent
from .core import Stop, gh, home, run, save


def issue_id(url):
    match = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/issues/([1-9]\d*)/?", url)
    if not match or any(p in {".", ".."} for p in match[1].split("/")):
        raise Stop("Enter a github.com issue URL.")
    return match[1], int(match[2])


def pages(endpoint):
    return [row for page in gh("api", "--paginate", "--slurp", endpoint) for row in page]


def evidence(repo, number, login, own_pr=None):
    issue = gh("api", f"repos/{repo}/issues/{number}")
    if ("pull_request" in issue or issue["state"] != "open" or issue["locked"]
            or any(a["login"] != login for a in issue["assignees"])):
        raise Stop(f"Issue is closed, locked, assigned to someone else, or a PR: {issue['html_url']}")
    comments = pages(f"repos/{repo}/issues/{number}/comments")
    timeline = pages(f"repos/{repo}/issues/{number}/timeline")
    linked = [e.get("source", {}).get("issue", {}) for e in timeline]
    competing = [i["html_url"] for i in linked if i.get("pull_request") and i["state"] == "open"
                 and i["html_url"] != own_pr]
    if competing:
        raise Stop("Open PR references this issue: " + ", ".join(competing))
    pulls = pages(f"repos/{repo}/pulls?state=open&per_page=100")
    return dict(issue=issue["html_url"], title=issue["title"], body=issue["body"],
                labels=[label["name"] for label in issue["labels"]],
                comments=[(c["html_url"], c["author_association"], c["body"]) for c in comments],
                open_prs=[(p["html_url"], p["title"]) for p in pulls if p["html_url"] != own_pr])


def git(cwd, *args):
    return run("git", "-c", "core.hooksPath=/dev/null", *args, cwd=cwd)


def checked(report, fields):
    if not report["proceed"] or not all(report[f] for f in fields):
        raise Stop(report["reason"] or "Agent could not verify the requirements.")


def transact(url, prefs, *, follow=None):
    repo, number = issue_id(url)
    root = home() / "runs" / repo.lower() / str(number)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop(f"Another process is handling {url}.")
        return work(root, repo, number, url, prefs, follow)


def work(root, repo, number, url, prefs, follow):
    path = root / "state.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    login = run("gh", "api", "user", "--jq", ".login")
    meta = gh("repo", "view", repo, "--json", "nameWithOwner,defaultBranchRef,isArchived,isPrivate")
    if meta["isArchived"] or meta["isPrivate"]:
        raise Stop("Discovery and publication require an active public repository.")
    base = meta["defaultBranchRef"]["name"]
    branch = f"oss-pilot/issue-{number}"
    if state and state["login"] != login:
        raise Stop("This run belongs to a different GitHub login.")
    if not state:
        state = dict(issue=url, repo=repo, base=base, branch=branch, login=login)
        save(path, state)
    branch, base = state["branch"], state["base"]
    prs = gh("api", "-X", "GET", f"repos/{repo}/pulls", "-f", "state=all",
             "-f", f"head={login}:{branch}", "-f", f"base={base}")
    pr = next(iter(prs), None)
    if pr:
        if not state.get("commit") or pr["user"]["login"] != login:
            raise Stop(f"Branch already has a PR: {pr['html_url']}")
        state["pr"] = pr["html_url"]
        save(path, state)
        if follow is None or pr["state"] != "open":
            print(f"{pr['state'].capitalize()} PR: {state['pr']}")
            return
    elif follow is not None or state.get("pr"):
        raise Stop("The saved PR could not be reconciled with GitHub.")
    context = evidence(repo, number, login, state.get("pr"))
    checkout = root / "checkout"
    if not checkout.exists():
        git(root, "clone", "--single-branch", "--branch", base, f"https://github.com/{repo}.git",
            str(checkout))
    if git(checkout, "branch", "--show-current") == base:
        git(checkout, "switch", "-c", branch)
    if git(checkout, "branch", "--show-current") != branch:
        raise Stop("Checkout is on an unexpected branch.")
    if not state.get("base_commit"):
        state["base_commit"] = git(checkout, "rev-parse", "HEAD")
        save(path, state)
    context.update(login=login, preferences=prefs, review_feedback=follow)
    scout = agent("scout", checkout,
                  "Inspect project rules, issue activity, similar PRs and proposals, assignment, "
                  "reward terms and prerequisites. Stop on a duplicate, unmet requirement, or upfront "
                  "cost. Confirm a reward only from specific authoritative evidence. Cite sources.",
                  context, {"reward_confirmed": "boolean"})
    state["scout"] = scout
    save(path, state)
    checked(scout, ["reward_confirmed"] if prefs["paid_only"] else [])
    if follow:
        context["previous_implementation"] = state.get("implementation")
    if not state.get("commit") or follow:
        impl = agent("implementer", checkout,
                     "Implement the selected issue or requested review changes. Inspect any partial "
                     "work already here. Reproduce the issue or demonstrate the requirement, add a "
                     "focused regression if appropriate, run relevant tests, and record commands "
                     "and actual outcomes. Stop if tests cannot pass. Leave changes uncommitted.",
                     context, {"reproduction": "string", "tests": "string"})
        state["implementation"] = impl
        save(path, state)
        checked(impl, ["reproduction", "tests"])
        git(checkout, "add", "-A")
        if not git(checkout, "diff", "--cached", "--name-only"):
            raise Stop("Implementation produced no changes. " + impl["reason"])
        git(checkout, "commit", "-m", context["title"])
        state["commit"] = git(checkout, "rev-parse", "HEAD")
        save(path, state)
    if git(checkout, "rev-parse", "HEAD") != state["commit"] or git(checkout, "status", "--porcelain"):
        raise Stop("Local checkout differs from the recorded commit.")
    with tempfile.TemporaryDirectory() as directory:
        review = Path(directory) / "review"
        git(root, "clone", "--no-local", str(checkout), str(review))
        context.update(base_commit=state["base_commit"], commit=state["commit"],
                       implementation=state["implementation"])
        report = agent("reviewer", review,
                       "Independently inspect the full base_commit..commit diff for correctness, "
                       "scope, unintended files and project rules. Rerun relevant tests yourself. "
                       "Approve only if all pass and the diff is ready. Report exact commands/results.",
                       context, {"tests": "string"})
        state["review"] = report
        save(path, state)
        checked(report, ["tests"])
        if git(review, "diff", "HEAD", "--name-only") or git(review, "rev-parse", "HEAD") != state["commit"]:
            raise Stop("Reviewer modified the reviewed source.")
    # Refresh issue and competing activity after the agents finish.
    latest = evidence(repo, number, login, state.get("pr"))
    if any(latest[key] != context[key] for key in latest):
        raise Stop("Issue or open PR activity changed during review. Resume to scout again.")
    publish(root, path, state, checkout, context)


def publish(root, path, state, checkout, context):
    repo, login, branch = state["repo"], state["login"], state["branch"]
    target = repo
    if repo.split("/")[0].lower() != login.lower():
        target = run("gh", "repo", "fork", repo, "--clone=false", "--remote=false", cwd=checkout)
        # Resolve the authenticated user's fork, including renamed forks.
        forks = pages(f"repos/{repo}/forks?per_page=100")
        fork = next((f for f in forks if f["owner"]["login"] == login), None)
        if not fork:
            raise Stop("Could not verify the destination fork.")
        target = fork["full_name"]
    git(checkout, "push", f"https://github.com/{target}.git", f"{state['commit']}:refs/heads/{branch}")
    if not state.get("pr"):
        impl = state["implementation"]
        body = (f"Closes {state['issue']}\n\n{impl['reason']}\n\n### Reproduction\n{impl['reproduction']}"
                f"\n\n### Implementation tests\n{impl['tests']}\n\n### Independent review\n"
                f"{state['review']['tests']}\n\nPrepared with Codex assistance.\n")
        body_path = root / "pr-body.md"
        body_path.write_text(body)
        state["pr"] = run("gh", "pr", "create", "-R", repo, "--base", state["base"], "--head",
                          branch if target == repo else f"{login}:{branch}", "--title", context["title"],
                          "--body-file", str(body_path), cwd=checkout)
    save(path, state)
    print(f"Reviewed commit {state['commit']} published: {state['pr']}")
