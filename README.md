# Freelancer Account Control Panel

Browser panel for a Freelancer multiplayer account archive. The app is now split into a small
entry point plus modules under `fl_panel/`, while browser styling and JavaScript live in
`fl_panel/static/` for easier editing.

## Project layout

- `account_panel.py` — tiny CLI entry point;
- `fl_panel/server.py` — HTTP routes, sessions and POST handlers;
- `fl_panel/repository.py` — account loading, authentication and business logic;
- `fl_panel/gamedata.py` — IONCROSS `GAMEDATA_*.txt` loader and code resolver;
- `fl_panel/finance.py` — `.fl` money and account `bank.ini` read/write helpers;
- `fl_panel/views.py` — HTML renderers;
- `fl_panel/static/index.html`, `style.css` and `tabs.js` — browser UI assets, including AJAX finance forms.

## Login compatibility

The login form accepts either:

1. a character name plus the account password from the account folder `name` file;
2. an account folder ID (`23-...`) with the optional character name field;
3. the old compatibility mode: account folder ID without a password.

This keeps the previous account-ID login flow available while still supporting the character
password login flow.

## Character cabinet tabs

- **Инвентарь** — cargo/inventory from the character save;
- **Снаряжение** — ship, mounted equipment and base equipment state;
- **Статистика** — time played, created/updated dates, kills, deaths and mission counters;
- **Финансы** — character money, `bank.ini` balance, direct pilot transfers, and bank
  deposit/withdrawal operations;
- **Репутация** — relations with factions resolved through `GAMEDATA_factions.txt`;
- **Навигация** — current system/base plus visited systems, bases, holes and map marks in a
  readable table where the local data allows code resolution.

## Financial operations

`bank.ini` is stored in the account folder as a single plain integer for speed:

```txt
1000000
```

Legacy `[Bank] balance = ...` files are still readable, but the panel writes the optimized
plain-number format after the next bank operation.

Supported operations from the **Финансы** tab are submitted with AJAX, so the cabinet balances update without a full page reload:

- **Transfer to another pilot**: enter the target pilot nickname and amount. The panel debits the
  sender character's in-game `money` first. If the character balance is not enough, the remainder
  is debited from the sender account's `bank.ini`. If character money plus bank balance is still
  insufficient, the operation is rejected.
- **Deposit to bank**: moves the amount from the current character's `.fl` `money` field into
  `bank.ini`.
- **Withdraw from bank**: moves the amount from `bank.ini` into the current character's `.fl`
  `money` field.

## Admin area

Administrative views are separated under `/admin`. They keep the operator search/listing and
JSON export away from the player login flow. Protect `/admin` with VPN/reverse-proxy auth before
publishing the service.


## Browser flight prototype

The panel also exposes a lightweight in-browser Freelancer-style flight prototype at
<http://127.0.0.1:8080/game>. It reuses the repository game data instead of hard-coded
content:

- `IONCROSS/GAMEDATA_systems.txt`, `GAMEDATA_bases.txt` and `GAMEDATA_ships.txt` populate
  the system picker, target names and ship selector;
- `DATA/UNIVERSE/SYSTEMS/<system>/<system>.ini` supplies object positions for planets,
  stations, suns, trade lanes and jump objects;
- `/api/game-data?system=Li01` returns the browser-safe JSON used by the canvas renderer.

Controls: `W/S` throttle, `A/D` turn, `Shift` afterburner, `Space` cruise impulse, `Tab`
selects the nearest target, and `M` dims the map panel.

## Run locally

```bash
python3 account_panel.py --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080>, then log in with a character name such as `Athlon0104`
and the decoded password from that account's `name` file, or use an account ID in compatibility
mode.

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

Financial actions write to `.fl` character files and account-level plain-number `bank.ini` files. Back up the
account archive before enabling this on a live server, and do not expose the app publicly without
transport security and access control.
