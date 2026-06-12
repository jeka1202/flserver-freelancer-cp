from __future__ import annotations

import json

from .flhook_client import FlHookClient, status_to_dict


def main() -> None:
    client = FlHookClient.from_config()
    print("FLHook diagnostic")
    print(f"host={client.config.host}")
    print(f"port={client.config.port}")
    print(f"encoding={client.config.encoding}")
    print(f"command={client.config.diagnostic_command}")
    print()

    status = client.status()
    print(json.dumps(status_to_dict(status), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
