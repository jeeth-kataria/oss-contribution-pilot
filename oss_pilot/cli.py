import sys

from .core import Stop, discover, home, preferences


def shortlist(prefs):
    issues = discover(prefs)
    if not issues:
        raise Stop("No matching open, unassigned issues found.")
    for n, issue in enumerate(issues, 1):
        print(f"{n}. {issue['title']} (updated {issue['updatedAt'][:10]})\n   {issue['url']}")
    return issues


def menu():
    prefs = preferences(home())
    print("1. Find opportunities\n2. Find one and open a PR\n3. Work on an issue URL\n4. Continue my PRs")
    choice = input("> ").strip()
    if choice == "1":
        shortlist(prefs)
    else:
        raise Stop("The discovery milestone supports choice 1.")


def main():
    try:
        menu()
    except (Stop, OSError, ValueError, KeyboardInterrupt, EOFError) as error:
        print(f"Stopped: {error or 'input cancelled'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
