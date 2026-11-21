# OSS Contribution Pilot

`oss-pilot` finds open-source issues, prepares a change in its own checkout, and opens a pull request after a second Codex session reviews the diff and reruns the tests. Discovery is read-only. A contribution run can open one upstream PR.

## Run locally

Use macOS or Linux, Python 3.10+, Git, an authenticated GitHub CLI, and a Git identity for commits. Discovery needs GitHub access. Implementation and review also need the Codex CLI with support for `exec --ignore-user-config --output-schema` and an existing ChatGPT login. Agent runs use that account’s available usage.

```sh
git clone https://github.com/jeeth-kataria/oss-contribution-pilot.git
cd oss-contribution-pilot
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
gh auth login
gh auth setup-git
codex login
oss-pilot
```

On first launch, press Enter for machine learning, inference, and agents in Python or TypeScript. Enable paid-only mode to require the scout to find authoritative reward terms before implementation. The workflow allows zero upfront spend.

| Menu choice | Outcome |
| --- | --- |
| Find opportunities | Search public, open, unassigned issues. Rank contributor-friendly labels first and then recent activity. Results link to the issues. Paid-only search uses advertised reward hints until the scout verifies terms. |
| Find one and open a PR | Take the first shortlisted issue through scouting, implementation, review, and publication. A failed check ends the run with its reason. |
| Work on an issue URL | Run the same workflow on the selected GitHub issue. Re-entering its URL resumes the local run. |
| Continue my PRs | Choose an unfinished run or one of your 100 most recently updated open public PRs. For a PR on your own topic branch, inspect maintainer feedback, implement outstanding requests, independently test the change, and push it to the existing PR. |

The scout reads contribution rules, assignments, issue comments, linked PRs, and open PR titles. A duplicate proposal, competing fix, unmet prerequisite, or unconfirmed required reward stops the run. The implementer records the reproduction and test commands. The independent reviewer gets a separate checkout. Publication uses the reviewed commit and includes both test reports in the PR body. The coordinator uses an owned branch or a GitHub fork for publication.

Preferences and run records live in `~/.local/share/oss-pilot`. Set `OSS_PILOT_HOME` to change that location. Each issue record includes the branch, commit, agent evidence and PR URL. PR follow-up records the previous head and feedback so a restart can recognize an already-published update. GitHub and Codex manage their own credentials. If validation requires unavailable dependencies or network access inside an agent sandbox, the run can stop with the missing prerequisite.

## Walkthrough

**Owned-repository acceptance run.** Choosing **Work on an issue URL** reproduced an unpaid listing appearing in paid-only search. The PR records the failing test before the change and passing implementation and review checks. Restarting found the same PR. Choosing **Continue my PRs** then added coverage for reward labels after a maintainer requested it. A second follow-up recognized the published commit. [Acceptance issue](https://github.com/jeeth-kataria/oss-contribution-pilot/issues/1) · [Reviewed fix and follow-up](https://github.com/jeeth-kataria/oss-contribution-pilot/pull/2)

**Firecrawl, historical example.** A Python SDK contribution used a fake clock to reproduce crawl polling beyond the caller’s deadline. Four cases failed before the fix. All ten deadline cases and 754 SDK unit tests passed afterward, as recorded in the PR. This illustrates the evidence the implementer should collect. [Firecrawl PR #5944](https://github.com/firecrawl/firecrawl/pull/5944)

**Expensify, historical example.** An investigation reproduced an address selector reverting to the saved state on a $250 listing. An earlier proposal already described the cause, so the contributor passed on submitting a duplicate. This illustrates a scout stop even when a bug is reproducible and a reward is advertised. [Expensify issue #102630](https://github.com/Expensify/App/issues/102630) · [Earlier proposal](https://github.com/Expensify/App/issues/102630#issuecomment-5907537065)

## Test

```sh
python3 -m unittest discover -s tests -v
```

The offline suite covers discovery filters, publication gates, evidence in the PR body, and restart handling. The acceptance PR above exercises the live GitHub and Codex paths.
