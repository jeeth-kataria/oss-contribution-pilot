import sys

from .core import Stop, discover, home, preferences
from .follow import continue_work

from .workflow import transact


def shortlist(prefs):
    issues = discover(prefs)
    if not issues:
        raise Stop("No matching open, unassigned issues found.")
    for n, issue in enumerate(issues, 1):
        labels = ", ".join(label["name"] for label in issue["labels"][:4])
        print(f"{n}. {issue['title']} (updated {issue['updatedAt'][:10]})\n   {issue['url']} {labels}".rstrip())
    return issues


def menu():
    prefs = preferences(home())
    print("1. Find opportunities\n2. Find one and open a PR\n3. Work on an issue URL\n4. Continue my PRs")
    choice = input("> ").strip()
    if choice == "1":
        shortlist(prefs)
    elif choice == "2":
        candidates = shortlist(prefs)
        transact(candidates[0]["url"], prefs)
    elif choice == "3":
        transact(input("Issue URL: ").strip(), prefs)
    elif choice == "4":
        continue_work(prefs)
    else:
        raise Stop("Choose a menu item from 1 to 4.")


def main():
    try:
        menu()
    except (Stop, OSError, ValueError, KeyboardInterrupt, EOFError) as error:
        print(f"Stopped: {error or 'input cancelled'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
