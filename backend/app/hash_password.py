"""Prompt for a password and print its bcrypt hash for DASHBOARD_PASSWORD_HASH."""

import getpass
import sys

from .auth import hash_password


def main() -> None:
    first = getpass.getpass("Dashboard password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("Passwords do not match", file=sys.stderr)
        sys.exit(1)
    if not first:
        print("Password must not be empty", file=sys.stderr)
        sys.exit(1)
    print(hash_password(first))


if __name__ == "__main__":
    main()
