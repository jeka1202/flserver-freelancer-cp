from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .flhook_client import FlHookError, FlHookUnavailable, FlHookResult


IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,}[0-9a-fA-F]{0,4}\b")


def admin_pilot_url(account_id: str, character_file: str) -> str:
    return f"/admin/pilot/{quote(str(account_id), safe='')}/{quote(str(character_file), safe='')}"


def _clean_player_name(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^\s*#?\d+\s*[:.)-]\s*", "", text)
    text = re.sub(r"^\s*(player|char|name|id)\s*[=:]\s*", "", text, flags=re.I)
    text = text.strip(" \t\r\n|;")
    return text


def _kv_value(line: str, keys: tuple[str, ...]) -> str:
    for key in keys:
        match = re.search(
            rf"\b{re.escape(key)}\s*[=:]\s*(\"[^\"]+\"|'[^']+'|[^\s|;]+)",
            line,
            flags=re.I,
        )
        if match:
            return match.group(1).strip().strip("\"'")
    return ""


def parse_getplayers_line(line: str) -> dict[str, Any]:
    raw = str(line or "").strip()
    entry = {
        "name": "",
        "ip": "",
        "system": "",
        "base": "",
        "place": "",
        "client_id": "",
        "raw": raw,
    }

    if not raw or raw.upper() == "OK" or raw.upper().startswith("ERR"):
        return entry

    client_match = re.search(r"\b(?:id|client|clientid)\s*[=:]\s*(\d+)\b", raw, flags=re.I)
    if client_match:
        entry["client_id"] = client_match.group(1)
    else:
        leading_id = re.match(r"^\s*#?(\d+)\s*[:.)-]\s*", raw)
        if leading_id:
            entry["client_id"] = leading_id.group(1)

    entry["name"] = _kv_value(raw, ("charname", "character", "char", "player", "name"))
    entry["system"] = clean_flhook_location_value(_kv_value(raw, ("system", "sys", "systemname")))
    entry["base"] = clean_flhook_location_value(_kv_value(raw, ("base", "station", "planet", "dock", "docked", "location", "loc")))
    entry["place"] = entry["base"]
    entry["ip"] = _kv_value(raw, ("ip", "addr", "address"))

    ip_match = IPV4_RE.search(raw) or IPV6_RE.search(raw)
    if ip_match and not entry["ip"]:
        entry["ip"] = ip_match.group(0)

    chunks = [chunk.strip() for chunk in re.split(r"\s+\|\s+|\t+|;", raw) if chunk.strip()]
    if chunks:
        if not entry["name"]:
            entry["name"] = _clean_player_name(chunks[0])

        # Common getplayers variants are "name | ip | system" or
        # "id | name | ip | system". These guesses are harmless if the line is
        # different: the raw line is also shown in the admin UI.
        if len(chunks) >= 2:
            for chunk in chunks[1:]:
                if not entry["ip"] and (IPV4_RE.search(chunk) or IPV6_RE.search(chunk)):
                    entry["ip"] = (IPV4_RE.search(chunk) or IPV6_RE.search(chunk)).group(0)
                    continue

                if not (IPV4_RE.search(chunk) or IPV6_RE.search(chunk)):
                    cleaned = clean_flhook_location_value(_clean_player_name(chunk))
                    if cleaned and cleaned.lower() != entry["name"].lower() and not re.fullmatch(r"\d+", cleaned):
                        if not entry["system"]:
                            entry["system"] = cleaned
                        elif not entry["base"] and cleaned.lower() != str(entry["system"]).lower():
                            entry["base"] = cleaned
                            entry["place"] = cleaned

    if not entry["name"]:
        before_ip = raw
        if ip_match:
            before_ip = raw[:ip_match.start()]
        entry["name"] = _clean_player_name(before_ip)

    # Remove key-value tail if it leaked into name.
    entry["name"] = re.split(r"\s+\b(?:ip|addr|system|sys|ping|loss|client|clientid)\s*[=:]", entry["name"], maxsplit=1, flags=re.I)[0].strip()

    return entry


def parse_getplayers_result(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        entry = parse_getplayers_line(raw)
        if entry.get("name"):
            result.append(entry)
    return result


def _find_character_fuzzy(repo: Any, name: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    exact = repo.find_unique_character(name)
    if isinstance(exact, tuple):
        return exact

    name_cf = str(name or "").casefold().strip()
    if not name_cf:
        return None

    # Fallback: some FLHook getplayers formats include extra columns inside the
    # parsed name. Try to find an archived character whose name is contained in
    # the raw token.
    for account in getattr(repo, "accounts", []):
        for character in account.get("characters", []):
            char_name = str(character.get("name") or "")
            if char_name and char_name.casefold() in name_cf:
                return account, character

    return None





def clean_flhook_location_value(value: str) -> str:
    """Clean raw FLHook getplayers fields like 'system=Li01' or 'base=Li01_01_Base'."""
    text = str(value or "").strip().strip("|;,'\"")
    text = re.sub(r"^(system|sys|systemname|base|station|planet|dock|docked|location|loc)\s*[=:]\s*", "", text, flags=re.I)
    text = text.strip().strip("|;,'\"")
    return text


def resolve_ui_token(repo: Any, value: str, *, fallback: str = "") -> str:
    """Resolve game nickname/hash to human UI name when possible.

    Prevents raw values like 'system=Li01' from leaking into UI.
    """
    token = clean_flhook_location_value(value)
    if not token:
        return fallback

    try:
        gamedata = getattr(repo, "gamedata", None)
        if gamedata:
            resolved = gamedata.resolve(token)
            name = str(resolved.get("name") or "").strip()
            code = str(resolved.get("code") or "").strip()
            nickname = str(resolved.get("nickname") or "").strip()
            if name and name.casefold() not in {"неизвестно", "unknown"}:
                return name
            if nickname and nickname.casefold() not in {"неизвестно", "unknown"}:
                return nickname
            if code and code.casefold() not in {"неизвестно", "unknown"}:
                return code
    except Exception:
        pass

    return token or fallback



UNKNOWN_PLACE_NAMES = {"", "—", "-", "неизвестно", "unknown", "none", "null"}


def file_system_name(character: dict[str, Any]) -> str:
    system = character.get("system") or {}
    for key in ("name", "display_name", "nickname", "token", "code"):
        value = clean_flhook_location_value(str(system.get(key) or "").strip())
        if value and value.casefold() not in UNKNOWN_PLACE_NAMES:
            return value
    return "—"


def file_place_name(character: dict[str, Any]) -> str:
    base = character.get("base") or {}
    for key in ("name", "display_name", "nickname", "token", "code"):
        value = clean_flhook_location_value(str(base.get(key) or "").strip())
        if value and value.casefold() not in UNKNOWN_PLACE_NAMES:
            return value
    return "в космосе"


def find_online_player_entry(repo: Any, character_name: str) -> dict[str, Any] | None:
    """Find current pilot row in FLHook getplayers output.

    This is used only for admin live location. If FLHook gives system/base in
    getplayers output, it is preferred over stale .fl file data.
    """
    try:
        flhook = getattr(repo, "flhook", None)
        if not flhook or not flhook.enabled:
            return None

        result = flhook.getplayers()
        if not result.ok:
            return None

        name_cf = str(character_name or "").casefold().strip()
        if not name_cf:
            return None

        for entry in parse_getplayers_result(result.text):
            entry_name = str(entry.get("name") or "").casefold().strip()
            raw_cf = str(entry.get("raw") or "").casefold()
            if entry_name == name_cf or name_cf in raw_cf:
                return entry

    except Exception:
        return None

    return None


def admin_live_location(repo: Any, character: dict[str, Any]) -> dict[str, Any]:
    """Best-effort live location for admin UI.

    Rules:
    1. Always start with freshly parsed .fl data.
    2. If pilot is online, do not trust stale `base =` from .fl as a final
       location, because the player can already be in space or docked elsewhere.
    3. If FLHook getplayers contains system/base/location, use it.
    4. If FLHook only confirms online but does not expose base/dock info,
       show the live system if available and mark place as "в космосе" instead
       of showing a stale planet/base from the save file.
    """
    name = str(character.get("name") or "").strip()
    file_system = file_system_name(character)
    file_place = file_place_name(character)

    payload = {
        "online": False,
        "system": file_system,
        "place": file_place,
        "source": "file",
        "raw": "",
        "has_live_place": False,
    }

    try:
        online = bool(repo.flhook_online(name)) if name else False
    except Exception:
        online = False

    if not online:
        return payload

    payload["online"] = True
    payload["source"] = "flhook_online"

    entry = find_online_player_entry(repo, name)
    if entry:
        payload["raw"] = entry.get("raw") or ""
        system = resolve_ui_token(repo, entry.get("system") or "", fallback="")
        place = resolve_ui_token(repo, entry.get("base") or entry.get("place") or "", fallback="")

        if system:
            payload["system"] = system
            payload["source"] = "flhook_getplayers"

        if place:
            payload["place"] = place
            payload["source"] = "flhook_getplayers"
            payload["has_live_place"] = True
            return payload

    # Online but no live dock/base value from FLHook.
    # Avoid false stale "Planet ..." from .fl while the pilot is actually in
    # space. If getplayers only gives a system, this is still more honest than
    # showing last docked planet as current.
    payload["place"] = "в космосе"
    return payload


def online_pilots(repo: Any) -> dict[str, Any]:
    payload = {
        "ok": False,
        "message": "",
        "raw": "",
        "lines": [],
        "players": [],
    }

    try:
        flhook = getattr(repo, "flhook", None)
        if not flhook or not flhook.enabled:
            payload["message"] = "FLHook выключен в конфиге."
            return payload

        result = flhook.getplayers()
        payload["ok"] = result.ok
        payload["raw"] = result.text
        payload["lines"] = result.lines

        entries = parse_getplayers_result(result.text)
        players: list[dict[str, Any]] = []
        for entry in entries:
            found = _find_character_fuzzy(repo, entry.get("name", ""))
            account: dict[str, Any] | None = None
            character: dict[str, Any] | None = None
            if found:
                account, character = found
                refreshed = repo.refresh_character(account.get("id", ""), character.get("file", ""))
                if refreshed:
                    account, character = refreshed

            system_name = resolve_ui_token(repo, entry.get("system") or "", fallback="")
            base_name = resolve_ui_token(repo, entry.get("base") or entry.get("place") or "", fallback="")
            ship_name = ""
            rank = ""
            money_value = 0
            account_id = ""
            character_file = ""
            url = ""

            if account and character:
                account_id = str(account.get("id") or "")
                character_file = str(character.get("file") or "")
                url = admin_pilot_url(account_id, character_file)
                live_location = admin_live_location(repo, character)
                system_name = system_name or str(live_location.get("system") or "")
                base_name = base_name or str(live_location.get("place") or "")
                ship_name = str((character.get("ship") or {}).get("name") or "")
                rank = str(character.get("rank") or "")
                money_value = int(character.get("money") or 0)

            players.append({
                "name": entry.get("name") or "",
                "ip": entry.get("ip") or "",
                "system": system_name,
                "system_raw": entry.get("system") or "",
                "base": base_name,
                "location_source": ("flhook" if (entry.get("system") or entry.get("base") or entry.get("place")) else "live/file"),
                "ship": ship_name,
                "rank": rank,
                "money": money_value,
                "account_id": account_id,
                "character_file": character_file,
                "url": url,
                "client_id": entry.get("client_id") or "",
                "raw": entry.get("raw") or "",
                "known": bool(account and character),
            })

        payload["players"] = players
        payload["message"] = f"Онлайн пилотов: {len(players)}" if result.ok else "FLHook ответил ошибкой."
        return payload

    except (FlHookUnavailable, FlHookError) as exc:
        payload["message"] = f"FLHook недоступен: {exc}"
        return payload
    except Exception as exc:
        payload["message"] = f"Ошибка чтения FLHook: {exc}"
        return payload


def run_admin_flhook_command(repo: Any, command: str) -> dict[str, Any]:
    command = str(command or "").strip()

    if not command:
        return {
            "ok": False,
            "command": "",
            "text": "Команда пустая.",
            "lines": [],
        }

    if len(command) > 2000:
        return {
            "ok": False,
            "command": command[:2000],
            "text": "Команда слишком длинная.",
            "lines": [],
        }

    try:
        flhook = getattr(repo, "flhook", None)
        if not flhook or not flhook.enabled:
            return {
                "ok": False,
                "command": command,
                "text": "FLHook выключен в конфиге.",
                "lines": [],
            }

        result: FlHookResult = flhook.command(command, timeout=flhook.config.timeout)
        return {
            "ok": result.ok,
            "command": command,
            "text": result.text,
            "lines": result.lines,
        }

    except Exception as exc:
        return {
            "ok": False,
            "command": command,
            "text": str(exc),
            "lines": [],
        }



def clamp_reputation(value: str | float) -> float:
    try:
        number = float(str(value).replace(",", ".").strip())
    except Exception:
        raise ValueError("Некорректное значение репутации.")

    if number < -1:
        number = -1.0
    if number > 1:
        number = 1.0

    return round(number, 3)


def reputation_changed(old_value: str | float, new_value: str | float) -> bool:
    try:
        old = clamp_reputation(old_value)
        new = clamp_reputation(new_value)
    except Exception:
        return False
    return abs(old - new) >= 0.001


def apply_admin_reputation_changes(repo: Any, character: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply edited faction reputation rows through FLHook."""
    result = {
        "ok": False,
        "message": "",
        "changed": 0,
        "commands": [],
        "errors": [],
    }

    charname = str(character.get("name") or "").strip()
    if not charname:
        result["message"] = "Не удалось определить имя пилота."
        return result

    flhook = getattr(repo, "flhook", None)
    if not flhook or not flhook.enabled:
        result["message"] = "FLHook выключен в конфиге."
        return result

    allowed_codes = {str(row.get("code") or "").strip(): row for row in character.get("houses", []) if str(row.get("code") or "").strip()}

    prepared: list[tuple[str, float, str]] = []
    for row in changes:
        code = str(row.get("code") or "").strip()
        if not code or code not in allowed_codes:
            continue

        old_value = row.get("old", allowed_codes[code].get("reputation", "0"))
        new_value = row.get("value", old_value)

        if not reputation_changed(old_value, new_value):
            continue

        try:
            value = clamp_reputation(new_value)
        except Exception as exc:
            result["errors"].append(f"{code}: {exc}")
            continue

        prepared.append((code, value, str(allowed_codes[code].get("name") or code)))

    if not prepared:
        result["ok"] = True
        result["message"] = "Изменений репутации нет."
        return result

    for code, value, name in prepared:
        try:
            flhook_result = flhook.set_reputation(charname, code, value)
            result["commands"].append({
                "code": code,
                "name": name,
                "value": value,
                "raw": flhook_result.text,
            })
            result["changed"] += 1
        except Exception as exc:
            result["errors"].append(f"{name} ({code}): {exc}")

    if result["changed"] and not result["errors"]:
        try:
            flhook.save_char(charname)
        except Exception:
            pass

        result["ok"] = True
        result["message"] = f"Репутация изменена: {result['changed']} строк."
        return result

    if result["changed"] and result["errors"]:
        result["ok"] = False
        result["message"] = f"Частично изменено: {result['changed']} строк. Ошибки: {'; '.join(result['errors'][:3])}"
        return result

    result["message"] = "Репутация не изменена. " + ("; ".join(result["errors"][:3]) if result["errors"] else "FLHook не принял команду.")
    return result

