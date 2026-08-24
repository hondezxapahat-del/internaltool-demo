"""Admin-only CLI to add a whitelisted account. There is no signup endpoint —
this script (or a direct SQL insert with a pre-hashed password) is the only
way a new account gets created. Usage: python create_user.py <username> <password>
"""

import sys

from auth import AuthError, create_user


def main():
    if len(sys.argv) != 3:
        print("Usage: python create_user.py <username> <password>")
        sys.exit(1)

    username, password = sys.argv[1], sys.argv[2]
    try:
        user = create_user(username, password)
    except AuthError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Created user '{user['username']}' (id={user['id']})")


if __name__ == "__main__":
    main()
