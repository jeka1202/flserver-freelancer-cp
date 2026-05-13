# Freelancer Account Control Panel

Read-only browser panel for the bundled Freelancer multiplayer account archive.
It reads character `.fl` files from `Accts/MultiPlayer` and translates numeric
ship/equipment/cargo/navigation codes through the local `IONCROSS/GAMEDATA_*.txt`
files.

## Client login

The client-facing page does **not** ask for an account-folder ID. A player enters:

1. character name from a `.fl` save;
2. the account-wide password stored in the account folder's `name` file.

After a successful match the panel opens only that character's personal cabinet.
All `.fl` files in one account folder share the same `name` password.

## Character cabinet tabs

- **Инвентарь** — cargo/inventory from the character save;
- **Снаряжение** — ship, mounted equipment and base equipment state;
- **Статистика** — time played, created/updated dates, kills, deaths and mission counters;
- **Финансы** — character money, future personal-bank balance and disabled placeholders for
  internal transfers/bank deposit/withdrawal flows;
- **Репутация** — relations with factions resolved through `GAMEDATA_factions.txt`;
- **Навигация** — current system/base plus visited systems, bases, holes and map marks in a
  readable table where the local data allows code resolution.

## Admin area

Administrative views are separated under `/admin`. They keep the operator search/listing and
JSON export away from the player login flow. Protect `/admin` with VPN/reverse-proxy auth before
publishing the service.

## Run locally

```bash
python3 account_panel.py --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>, then log in with a character name such as `Athlon0104`
and the decoded password from that account's `name` file.

## Custom paths

```bash
python3 account_panel.py \
  --accounts /path/to/Accts/MultiPlayer \
  --ioncross /path/to/IONCROSS \
  --host 0.0.0.0 \
  --port 8080
```

Environment variables `FL_PANEL_HOST` and `FL_PANEL_PORT` can also set the listen address
and port.

## Security note

The panel is intentionally read-only for save files. The future bank/transfer controls are UI
placeholders and currently do not write to `.fl` files. Do not expose the app publicly without
adding real transport security and access control.
