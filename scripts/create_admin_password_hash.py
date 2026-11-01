from __future__ import annotations

import getpass

from mongodb_vector_test_ui.core.admin_auth import hash_password


def main() -> None:
    password = getpass.getpass("New admin password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    try:
        print(hash_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
