"""Run one committed pytest selection against a pair of revisions."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from .core import Stop


def git(cwd, *args):
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd,
                            capture_output=True, text=True)
    if result.returncode:
        raise Stop(result.stderr.strip())
    return result.stdout.strip()


def observe(tree, subdir, selector, temp, timeout):
    work = tree / subdir
    observations = temp / (tree.name + ".jsonl")
    # Prefer the candidate source over any editable install of the caller's checkout.
    paths = [work, work / "src", tree / "src", temp]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, paths)),
               OSS_PILOT_OBSERVATIONS=str(observations), PYTEST_ADDOPTS="")
    command = ["-m", "pytest", "-p", "_pytest_probe", "-raP", "-q", "--color=no", "--", selector]
    start = time.monotonic()
    try:
        proc = subprocess.run([sys.executable, *command], cwd=work, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                              errors="replace")
        code, output = proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        code, output = None, f"Timed out after {timeout} seconds."
    rows = [json.loads(line) for line in observations.read_text().splitlines()] if observations.exists() else []
    def clean(value):
        for private in (str(work), str(tree), str(temp), str(Path.home()), sys.prefix):
            value = value.replace(private, "<local>")
        return re.sub(r'/(?:private/|var/|Users/|home/|opt/|tmp/)[^\s:]+', '<local-path>', value)
    for row in rows:
        row["error"] = clean(row["error"])
    return dict(code=code, output=clean(output), rows=rows, seconds=time.monotonic()-start,
                command=shlex.join(["python", "-m", "pytest", "-raP", "-q", "--", selector]))


def verdict(before, after):
    for run in (before, after):
        if run["code"] not in (0, 1) or not run["rows"]:
            return "Inconclusive", "Pytest did not complete the selected tests."
        if any(r["phase"] != "call" or r["outcome"] == "skipped" or r["xfail"] for r in run["rows"]):
            return "Inconclusive", "A fixture, skip, or expected failure affected this comparison."
    if sorted(r["node"] for r in before["rows"]) != sorted(r["node"] for r in after["rows"]):
        return "Inconclusive", "The revisions ran different test selections."
    for run in (before, after):
        failures = [r for r in run["rows"] if r["outcome"] == "failed"]
        if (run["code"] == 1) != bool(failures):
            return "Inconclusive", "Pytest exit status and test observations disagree."
        if any(not re.match(r"(AssertionError\b|assert\s|Failed: DID NOT (RAISE|WARN))", r["error"]) for r in failures):
            return "Inconclusive", "A test raised an error outside a recognized behavioral assertion."
    if after["code"]:
        return "Failing on the fix", "The selected assertion still fails at HEAD."
    if before["code"]:
        return "Reproduced before, passed after", "The same selection failed on the base and passed on the fix."
    return "This test did not distinguish the fix", "The selection passed on both revisions."


def report(title, reason, selector, runs):
    esc = html.escape
    sections = []
    for label, sha, run in runs:
        nodes = "\n".join(r["node"] + "  " + r["outcome"] + "  " + r["error"] for r in run["rows"])
        sections.append(f"<section><h2>{label}</h2><code>{sha}</code> · {run['seconds']:.2f} s"
                        f"<pre>{esc(nodes)}</pre><details><summary>Command and output</summary>"
                        f"<pre>{esc(run['command'])}\n{esc(run['output'])}</pre></details></section>")
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'
            'body{max-width:60rem;margin:auto;padding:3vw;font:17px/1.5 system-ui;color:#152e37}'
            'h1{line-height:1.1}section{border-top:1px solid #acbdc0;margin:2rem 0}pre,code{'
            'white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}</style><main>'
            f'<p>OSS Contribution Pilot · Regression proof</p><h1>{esc(title)}</h1><p>{esc(reason)}</p>'
            f'<code>{esc(selector)}</code>'+''.join(sections)+'</main></html>')


def prove(argv):
    parser = argparse.ArgumentParser(prog="oss-pilot prove")
    parser.add_argument("--base", required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.base.startswith("-"):
        raise Stop("Use a positive timeout and a Git revision.")
    cwd = Path.cwd()
    root = Path(git(cwd, "rev-parse", "--show-toplevel")).resolve()
    subdir = cwd.relative_to(root)
    file, sep, node = args.test.partition("::")
    path = Path(file)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
        raise Stop("Select a relative pytest file or node within the checkout.")
    head = git(root, "rev-parse", "HEAD")
    base = git(root, "merge-base", head, args.base)
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp).resolve()
        shutil.copyfile(Path(__file__).with_name("_pytest_probe.py"), temp / "_pytest_probe.py")
        trees = []
        try:
            for label, sha in (("base", base), ("head", head)):
                tree = temp / label
                git(root, "worktree", "add", "--detach", str(tree), sha)
                trees.append(tree)
            files = [tree / subdir / path for tree in trees]
            if any(f.resolve() != f for f in files) or not files[1].is_file():
                raise Stop("Select a committed regular test file without symlinks.")
            files[0].parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(files[1], files[0])
            runs = [(label, sha, observe(tree, subdir, str(path)+sep+node, temp, args.timeout))
                    for tree, label, sha in zip(trees, ("Base", "Fix"), (base, head))]
        finally:
            for tree in reversed(trees):
                git(root, "worktree", "remove", "--force", str(tree))
    title, reason = verdict(runs[0][2], runs[1][2])
    output = args.output or Path(tempfile.mkdtemp(prefix="oss-proof-")) / "report.html"
    output.write_text(report(title, reason, args.test, runs), encoding="utf-8")
    print(f"{title}\n{reason}\n{output.resolve()}")
    return 0 if title.startswith("Reproduced") else 1
