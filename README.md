# Freelancer Account Control Panel

Browser panel for the bundled Freelancer multiplayer account archive. It reads
character `.fl` files from `Accts/MultiPlayer`, translates numeric
ship/equipment/cargo/navigation codes through the local `IONCROSS/GAMEDATA_*.txt`
files, and can update player finances.

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
- **Финансы** — character money, `bank.ini` balance, direct pilot transfers, and bank
  deposit/withdrawal operations;
- **Репутация** — relations with factions resolved through `GAMEDATA_factions.txt`;
- **Навигация** — current system/base plus visited systems, bases, holes and map marks in a
  readable table where the local data allows code resolution.

## Financial operations

`bank.ini` is stored in the account folder and uses section `[Bank]` with field `balance`:

```ini
[Bank]
balance = 1000000
```

Supported operations from the **Финансы** tab:

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

Financial actions write to `.fl` character files and account-level `bank.ini` files. Back up the
account archive before enabling this on a live server, and do not expose the app publicly without
transport security and access control.
