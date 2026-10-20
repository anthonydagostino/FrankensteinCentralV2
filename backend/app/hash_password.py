"""Prompt for a password and print its bcrypt hash for DASHBOARD_PASSWORD_HASH."""

import getpass
import sys

import bcrypt


def main() -> None:
    first = getpass.getpass("Dashboard password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("Passwords do not match", file=sys.stderr)
        sys.exit(1)
    if not first:
        print("Password must not be empty", file=sys.stderr)
        sys.exit(1)
    print(bcrypt.hashpw(first.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"))


if __name__ == "__main__":
    main()
