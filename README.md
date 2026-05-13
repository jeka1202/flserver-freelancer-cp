# Freelancer Account Control Panel

Read-only browser panel for the bundled Freelancer multiplayer account archive.
It reads character `.fl` files from `Accts/MultiPlayer` and translates numeric
ship/equipment/cargo codes through the local `IONCROSS/GAMEDATA_*.txt` files.

## Features

- player login by account-folder ID (`23-...`) with optional character-name check;
- character summary: rank, credits, kills, mission counters, ship, current system,
  current base and last base;
- readable equipment and cargo names resolved from IONCROSS data files;
- full faction reputation table using `GAMEDATA_factions.txt`;
- admin search page for local operators at `/admin`;
- JSON export at `/api/accounts` for integrations;
- no external Python dependencies.

> Security note: this repository does not contain real account passwords. Do not
> publish `/admin` or `/account/...` directly to the internet without adding a
> proper authentication layer, VPN, or reverse-proxy access control.

## Run locally

```bash
python3 account_panel.py --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>, then log in with an account directory such as
`23-f73f713c`. If you enter a character name, it must belong to that account.

## Custom paths

```bash
python3 account_panel.py \
  --accounts /path/to/Accts/MultiPlayer \
  --ioncross /path/to/IONCROSS \
  --host 0.0.0.0 \
  --port 8080
```

Environment variables `FL_PANEL_HOST` and `FL_PANEL_PORT` can also set the
listen address and port.
