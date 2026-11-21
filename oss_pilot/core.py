import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


class Stop(Exception):
    """A specific reason the coordinator could not continue."""


def run(*args, cwd=None, stdin=None):
    result = subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True)
    if result.returncode:
        raise Stop(result.stderr.strip()[-3000:] or f"{args[0]} exited {result.returncode}")
    return result.stdout.strip()


def gh(*args):
    return json.loads(run("gh", *args))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(handle.name, path)


def home():
    return Path(os.environ.get("OSS_PILOT_HOME", "~/.local/share/oss-pilot")).expanduser().resolve()


def preferences(root):
    path = root / "preferences.json"
    if path.exists():
        return json.loads(path.read_text())
    def items(label, default):
        line = input(f"{label} [{default}] ").strip() or default
        values = [value.strip() for value in line.split(",") if value.strip()]
        if not values:
            raise Stop(f"Enter at least one value for {label}.")
        return values

    prefs = dict(topics=items("Topics", "machine-learning, inference, agents"),
                 languages=items("Languages", "Python, TypeScript"),
                 paid_only=input("Confirmed rewards only? [y/N] ").lower() in {"yes", "y"})
    save(path, prefs)
    return prefs


def discover(prefs):
    issues = {}
    for topic in prefs["topics"]:
        for language in prefs["languages"]:
            matches = gh("search", "issues", topic, "--language", language, "--state", "open",
                         "--visibility", "public", "--no-assignee", "--archived=false",
                         "--sort", "updated", "--limit", "8", "--json",
                         "url,title,labels,updatedAt,isLocked")
            for issue in matches:
                if issue["isLocked"]:
                    continue
                words = " ".join([issue["title"], *(i["name"] for i in issue["labels"])]).lower()
                if prefs["paid_only"] and not (
                    any(w in words for w in ("bounty", "reward", "$")) or re.search(r"\bpaid\b", words)
                ):
                    continue
                issues.setdefault(issue["url"], issue)
    def rank(issue):
        labels = {label["name"].lower() for label in issue["labels"]}
        welcoming = bool(labels & {"good first issue", "help wanted", "up for grabs"})
        return welcoming, issue["updatedAt"]

    return sorted(issues.values(), key=rank, reverse=True)[:10]
