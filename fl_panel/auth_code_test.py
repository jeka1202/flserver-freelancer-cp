from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ACCOUNTS_DIR, IONCROSS_DIR
from .repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Test pilot name + *-givecash.ini auth code.")
    parser.add_argument("pilot", help="Exact in-game pilot name")
    parser.add_argument("code", help="Code entered by pilot")
    parser.add_argument("--accounts", type=Path, default=ACCOUNTS_DIR)
    parser.add_argument("--ioncross", type=Path, default=IONCROSS_DIR)
    args = parser.parse_args()

    repo = Repository(args.accounts, args.ioncross)
    match = repo.authenticate(args.pilot, args.code)

    payload = {
        "pilot": args.pilot,
        "ok": bool(match),
        "diagnostic": "OK" if match else repo.debug_auth_login(args.pilot, args.code),
    }

    if match:
        _account, character = match
        payload["file"] = character.get("file")
        payload["auth_files"] = character.get("auth_code_files", [])

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
