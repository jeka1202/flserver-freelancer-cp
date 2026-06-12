from __future__ import annotations

import json
import os
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ROOT


CONFIG_PATH = Path(__file__).resolve().parent / "flhook_config.json"


class FlHookError(RuntimeError):
    pass


class FlHookUnavailable(FlHookError):
    pass


@dataclass
class FlHookConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 1920
    password: str = "test"
    encoding: str = "utf-16le"
    timeout: float = 3.0
    auth_command: str = "pass"
    diagnostic_command: str = "getplayers"


@dataclass
class FlHookResult:
    ok: bool
    text: str
    lines: list[str]


@dataclass
class FlHookStatus:
    enabled: bool
    connected: bool
    authenticated: bool
    ok: bool
    host: str
    port: int
    encoding: str
    command: str
    raw: str
    lines: list[str]
    players: list[str]
    message: str


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def load_flhook_config() -> FlHookConfig:
    data = _read_json_file(CONFIG_PATH)

    # Environment overrides are useful for temporary tests without editing files.
    if os.environ.get("FLHOOK_ENABLED") is not None:
        data["enabled"] = os.environ.get("FLHOOK_ENABLED", "").strip().lower() not in {"0", "false", "no", "off"}
    if os.environ.get("FLHOOK_HOST"):
        data["host"] = os.environ["FLHOOK_HOST"]
    if os.environ.get("FLHOOK_PORT"):
        data["port"] = os.environ["FLHOOK_PORT"]
    if os.environ.get("FLHOOK_PASSWORD") is not None:
        data["password"] = os.environ.get("FLHOOK_PASSWORD", "")
    if os.environ.get("FLHOOK_ENCODING"):
        data["encoding"] = os.environ["FLHOOK_ENCODING"]
    if os.environ.get("FLHOOK_TIMEOUT"):
        data["timeout"] = os.environ["FLHOOK_TIMEOUT"]
    if os.environ.get("FLHOOK_AUTH_COMMAND"):
        data["auth_command"] = os.environ["FLHOOK_AUTH_COMMAND"]
    if os.environ.get("FLHOOK_DIAGNOSTIC_COMMAND"):
        data["diagnostic_command"] = os.environ["FLHOOK_DIAGNOSTIC_COMMAND"]

    return FlHookConfig(
        enabled=bool(data.get("enabled", True)),
        host=str(data.get("host") or "127.0.0.1"),
        port=int(data.get("port") or 1920),
        password=str(data.get("password") or ""),
        encoding=str(data.get("encoding") or "utf-16le"),
        timeout=float(data.get("timeout") or 3.0),
        auth_command=str(data.get("auth_command") or "pass"),
        diagnostic_command=str(data.get("diagnostic_command") or "getplayers"),
    )


class FlHookClient:
    """FLHook WPort/Unicode socket client.

    Default target is FLHook [Socket] WPort=1920, so commands are sent as
    UTF-16LE strings. The protocol confirmed in testing is:

      connect
      <- Welcome to FLHack, please authenticate
      -> pass PASSWORD
      <- OK
      -> command
      <- result lines + OK
      -> quit

    If there are no online players, getplayers legitimately returns only OK.
    """

    def __init__(self, config: FlHookConfig | None = None) -> None:
        self.config = config or load_flhook_config()

    @classmethod
    def from_config(cls) -> "FlHookClient":
        return cls(load_flhook_config())

    @classmethod
    def from_env(cls) -> "FlHookClient":
        # Backward compatibility for repository.py from older panel versions.
        # Environment variables still override flhook_config.json inside load_flhook_config().
        return cls(load_flhook_config())

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.port > 0)

    def _decode(self, raw: bytes) -> str:
        if not raw:
            return ""
        encodings = [self.config.encoding, "utf-16le", "utf-8", "cp1251", "latin1"]
        for enc in encodings:
            try:
                return raw.decode(enc, errors="ignore").replace("\x00", "")
            except Exception:
                pass
        return raw.decode("latin1", errors="ignore").replace("\x00", "")

    def _encode(self, text: str) -> bytes:
        if not text.endswith("\n"):
            text += "\n"
        return text.encode(self.config.encoding, errors="ignore")

    @staticmethod
    def _clean_lines(text: str) -> list[str]:
        lines = []
        for line in text.replace("\r", "\n").split("\n"):
            cleaned = line.strip()
            if cleaned:
                lines.append(cleaned)
        return lines

    def _recv_text(self, sock: socket.socket, timeout: float | None = None, *, stop_after_first_chunk: bool = False) -> str:
        timeout = float(timeout if timeout is not None else self.config.timeout)
        chunks: list[bytes] = []
        end = time.time() + timeout
        sock.settimeout(min(0.1, max(0.02, timeout)))

        while time.time() < end:
            try:
                chunk = sock.recv(65535)
            except socket.timeout:
                continue
            if not chunk:
                break

            chunks.append(chunk)

            if stop_after_first_chunk:
                break

            text = self._decode(b"".join(chunks))
            lines = self._clean_lines(text)

            # FLHook command responses normally end with OK/ERR/Goodbye.
            if lines:
                last = lines[-1].lower()
                if last == "ok" or last.startswith("err") or "goodbye" in last:
                    break

        return self._decode(b"".join(chunks)).strip()

    def _send(self, sock: socket.socket, command: str) -> None:
        sock.sendall(self._encode(command.strip()))

    # v73 performance note:
    # Old implementation waited 1.5s for the Welcome banner and 0.5s for Goodbye
    # on every command. A warehouse operation may call 3-4 FLHook commands, so that
    # alone made the UI wait 6-8 seconds. Welcome is now read as one chunk and quit
    # is sent without waiting for a reply.
    def command(self, command: str, timeout: float | None = None) -> FlHookResult:
        if not self.enabled:
            raise FlHookUnavailable("FLHook socket disabled in flhook_config.json")

        command = str(command or "").strip()
        if not command:
            raise FlHookError("Empty FLHook command")

        try:
            with socket.create_connection((self.config.host, self.config.port), timeout=self.config.timeout) as sock:
                sock.settimeout(self.config.timeout)

                # Welcome banner is not terminated by OK, so do not wait full timeout.
                _welcome = self._recv_text(sock, timeout=0.25, stop_after_first_chunk=True)

                if self.config.password:
                    self._send(sock, f"{self.config.auth_command} {self.config.password}")
                    auth_text = self._recv_text(sock, timeout=timeout)
                    auth_lines = self._clean_lines(auth_text)
                    auth_upper = auth_text.upper()
                    if "OK" not in auth_upper or any(line.upper().startswith("ERR") for line in auth_lines):
                        raise FlHookError(f"FLHook auth failed: {auth_text or 'no response'}")

                self._send(sock, command)
                text = self._recv_text(sock, timeout=timeout)

                try:
                    # Do not wait for Goodbye here. Closing the socket is enough and saves
                    # ~0.5s per FLHook command.
                    self._send(sock, "quit")
                except Exception:
                    pass

        except OSError as exc:
            raise FlHookUnavailable(f"FLHook socket unavailable: {exc}") from exc

        lines = self._clean_lines(text)
        has_error = any(line.upper().startswith("ERR") for line in lines)
        has_ok = any(line.upper() == "OK" for line in lines)
        return FlHookResult(ok=has_ok and not has_error, text=text, lines=lines)


    @staticmethod
    def _quote_charname(charname: str) -> str:
        # FLHook ArgCharname is space-separated; current project pilot names
        # are expected to be single-token nicknames. Keep as-is.
        return str(charname or "").strip()

    @staticmethod
    def _parse_key_value_int(text: str, key: str) -> int:
        match = re.search(rf"\b{re.escape(key)}=(-?\d+)\b", text, re.IGNORECASE)
        if not match:
            raise FlHookError(f"FLHook response has no {key}=...: {text}")
        return int(match.group(1))

    def get_cash(self, charname: str) -> int:
        result = self.command(f"getcash {self._quote_charname(charname)}")
        if not result.ok:
            raise FlHookError(result.text)
        return self._parse_key_value_int(result.text, "cash")

    def add_cash(self, charname: str, amount: int) -> int:
        result = self.command(f"addcash {self._quote_charname(charname)} {int(amount)}")
        if not result.ok:
            raise FlHookError(result.text)
        return self._parse_key_value_int(result.text, "cash")

    def set_cash(self, charname: str, amount: int) -> int:
        result = self.command(f"setcash {self._quote_charname(charname)} {int(amount)}")
        if not result.ok:
            raise FlHookError(result.text)
        return self._parse_key_value_int(result.text, "cash")

    def is_logged_in(self, charname: str) -> bool:
        result = self.command(f"isloggedin {self._quote_charname(charname)}")
        if not result.ok:
            return False
        match = re.search(r"\bloggedin=(yes|no)\b", result.text, re.IGNORECASE)
        return bool(match and match.group(1).lower() == "yes")

    def is_on_server(self, charname: str) -> bool:
        result = self.command(f"isonserver {self._quote_charname(charname)}")
        if not result.ok:
            return False
        match = re.search(r"\bonserver=(yes|no)\b", result.text, re.IGNORECASE)
        return bool(match and match.group(1).lower() == "yes")

    def enum_cargo(self, charname: str) -> FlHookResult:
        return self.command(f"enumcargo {self._quote_charname(charname)}")

    def remaining_hold_size(self, charname: str) -> int | None:
        result = self.enum_cargo(charname)
        if not result.ok:
            raise FlHookError(result.text)
        match = re.search(r"\bremainingholdsize=(-?\d+)\b", result.text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    def add_cargo(self, charname: str, good: str, count: int, mission: int = 0) -> FlHookResult:
        good = str(good or "").strip()
        if not good:
            raise FlHookError("Good nickname is empty.")
        result = self.command(f"addcargo {self._quote_charname(charname)} {good} {int(count)} {int(mission)}")
        if not result.ok:
            raise FlHookError(result.text)
        return result

    def remove_cargo(self, charname: str, cargo_id: int, count: int) -> FlHookResult:
        result = self.command(f"removecargo {self._quote_charname(charname)} {int(cargo_id)} {int(count)}")
        if not result.ok:
            raise FlHookError(result.text)
        return result

    def save_char(self, charname: str) -> FlHookResult:
        result = self.command(f"savechar {self._quote_charname(charname)}")
        if not result.ok:
            raise FlHookError(result.text)
        return result



    @staticmethod
    def parse_enum_cargo(text: str) -> list[dict[str, int]]:
        cargo: list[dict[str, int]] = []
        for line in str(text or "").replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line or line.upper() == "OK" or line.lower().startswith("remainingholdsize="):
                continue
            values: dict[str, int] = {}
            for key in ("id", "archid", "count", "mission"):
                match = re.search(rf"\b{key}=(-?\d+)\b", line, re.IGNORECASE)
                if match:
                    values[key] = int(match.group(1))
            if {"id", "archid", "count"}.issubset(values):
                cargo.append(values)
        return cargo

    def enum_cargo_items(self, charname: str) -> list[dict[str, int]]:
        result = self.enum_cargo(charname)
        if not result.ok:
            raise FlHookError(result.text)
        return self.parse_enum_cargo(result.text)


    @staticmethod
    def archid_candidates(value: str | int) -> set[str]:
        raw = str(value or "").strip()
        candidates = {raw} if raw else set()

        try:
            number = int(raw, 0)
        except Exception:
            return candidates

        unsigned = number & 0xFFFFFFFF
        signed = unsigned - 0x100000000 if unsigned >= 0x80000000 else unsigned

        candidates.add(str(number))
        candidates.add(str(unsigned))
        candidates.add(str(signed))
        return candidates

    def remove_cargo_by_archid(self, charname: str, archid: str | int, count: int) -> FlHookResult:
        target_archids = self.archid_candidates(archid)
        left = int(count)
        if left <= 0:
            raise FlHookError("Cargo count must be positive.")

        matches = [row for row in self.enum_cargo_items(charname) if str(row.get("archid")) in target_archids]
        available = sum(int(row.get("count", 0)) for row in matches)

        if available < left:
            raise FlHookError(f"Not enough cargo in hold: requested {left}, available {available}.")

        last_result = FlHookResult(ok=True, text="OK", lines=["OK"])
        for row in matches:
            if left <= 0:
                break
            take = min(left, int(row.get("count", 0)))
            last_result = self.remove_cargo(charname, int(row["id"]), take)
            left -= take

        return last_result



    def set_reputation(self, charname: str, faction_code: str, value: float) -> FlHookResult:
        """Set character reputation through FLHook.

        Different FLHook builds/plugins may name the command slightly differently.
        The normal/default command tried first is:
          setrep <charname> <faction_code> <value>

        If it is unknown, we try common aliases before returning the last error.
        """
        charname = self._quote_charname(charname)
        faction_code = str(faction_code or "").strip()
        if not charname:
            raise FlHookError("Character name is empty.")
        if not faction_code:
            raise FlHookError("Faction code is empty.")

        rep = max(-1.0, min(1.0, float(value)))
        rep_text = f"{rep:.6f}".rstrip("0").rstrip(".")
        if rep_text in {"-0", "+0", ""}:
            rep_text = "0"

        commands = [
            f"setrep {charname} {faction_code} {rep_text}",
            f"setreputation {charname} {faction_code} {rep_text}",
            f"setrepbyname {charname} {faction_code} {rep_text}",
        ]

        last_result: FlHookResult | None = None
        for command in commands:
            result = self.command(command, timeout=self.config.timeout)
            last_result = result
            if result.ok:
                return result

            # If command exists but rejected value/char/faction, do not try
            # aliases that may have a different argument order.
            text = (result.text or "").lower()
            if "not found" in text or "invalid char" in text or "invalid faction" in text:
                break

        raise FlHookError(last_result.text if last_result else "FLHook reputation command failed.")


    def getplayers(self) -> FlHookResult:
        return self.command(self.config.diagnostic_command or "getplayers", timeout=self.config.timeout)

    @staticmethod
    def parse_players_from_getplayers(text: str) -> list[str]:
        players: list[str] = []
        for raw in text.replace("\r", "\n").split("\n"):
            line = raw.strip()
            if not line or line.upper() == "OK":
                continue
            if line.upper().startswith("ERR"):
                continue

            # Accept both plain names and common list formats:
            # "1: Player", "Player = 12 |", "Player | system | ..."
            chunks = [p.strip() for p in re.split(r"\s+\|\s+", line) if p.strip()]
            candidate = chunks[0] if chunks else line
            candidate = re.sub(r"^\s*\d+\s*[:.)-]\s*", "", candidate)
            candidate = re.sub(r"\s*=\s*\d+\s*$", "", candidate).strip()
            if candidate:
                players.append(candidate)
        return players

    def status(self, current_character: str = "") -> FlHookStatus:
        cfg = self.config
        if not self.enabled:
            return FlHookStatus(
                enabled=False,
                connected=False,
                authenticated=False,
                ok=False,
                host=cfg.host,
                port=cfg.port,
                encoding=cfg.encoding,
                command=cfg.diagnostic_command,
                raw="",
                lines=[],
                players=[],
                message="FLHook выключен в flhook_config.json",
            )

        try:
            result = self.getplayers()
            players = self.parse_players_from_getplayers(result.text)
            message = "FLHook подключён"
            if result.ok and not players:
                message = "FLHook подключён, онлайн-игроков нет"
            elif result.ok:
                message = f"FLHook подключён, онлайн: {len(players)}"
            return FlHookStatus(
                enabled=True,
                connected=True,
                authenticated=True,
                ok=result.ok,
                host=cfg.host,
                port=cfg.port,
                encoding=cfg.encoding,
                command=cfg.diagnostic_command,
                raw=result.text,
                lines=result.lines,
                players=players,
                message=message,
            )
        except FlHookError as exc:
            return FlHookStatus(
                enabled=True,
                connected=False,
                authenticated=False,
                ok=False,
                host=cfg.host,
                port=cfg.port,
                encoding=cfg.encoding,
                command=cfg.diagnostic_command,
                raw="",
                lines=[],
                players=[],
                message=str(exc),
            )


def flhook_status(current_character: str = "") -> FlHookStatus:
    return FlHookClient.from_config().status(current_character=current_character)


def status_to_dict(status: FlHookStatus, current_character: str = "") -> dict[str, Any]:
    current_character = str(current_character or "")
    online_names = {p.lower() for p in status.players}
    current_online = bool(current_character and current_character.lower() in online_names)
    return {
        "enabled": status.enabled,
        "connected": status.connected,
        "authenticated": status.authenticated,
        "ok": status.ok,
        "host": status.host,
        "port": status.port,
        "encoding": status.encoding,
        "command": status.command,
        "message": status.message,
        "raw": status.raw,
        "lines": status.lines,
        "players": status.players,
        "online_count": len(status.players),
        "current_character": current_character,
        "current_character_online": current_online,
    }


if __name__ == "__main__":
    st = flhook_status()
    payload = status_to_dict(st)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
