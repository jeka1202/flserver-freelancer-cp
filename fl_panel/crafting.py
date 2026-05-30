from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .gamedata import GameData
from .utils import nickname_hash, read_text, split_csv


class CraftingRecipe:
    def __init__(self, id: str, result: str, amount: int, ingredients: dict[str, int], station: str, tier: int, description: str = "") -> None:
        self.id = id
        self.result = result
        self.amount = amount
        self.ingredients = ingredients
        self.station = station
        self.tier = tier
        self.description = description


class CraftingSystem:
    def __init__(self, recipes_path: Path, gamedata: GameData) -> None:
        self.path = recipes_path
        self.gamedata = gamedata
        self.base_resources: list[str] = []
        self.recipes: list[CraftingRecipe] = []
        self.by_id: dict[str, CraftingRecipe] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.base_resources = []
            self.recipes = []
            self.by_id = {}
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.base_resources = [str(item) for item in payload.get("base_resources", [])]
        recipes = []
        for raw in payload.get("recipes", []):
            ingredients = {str(key): max(1, int(value)) for key, value in raw.get("ingredients", {}).items()}
            recipe = CraftingRecipe(
                id=str(raw.get("id") or raw.get("result") or "").strip(),
                result=str(raw.get("result") or "").strip(),
                amount=max(1, int(raw.get("amount", 1))),
                ingredients=ingredients,
                station=str(raw.get("station", "factory")),
                tier=max(1, int(raw.get("tier", 1))),
                description=str(raw.get("description", "")),
            )
            if recipe.id and recipe.result and recipe.ingredients:
                recipes.append(recipe)
        self.recipes = recipes
        self.by_id = {recipe.id: recipe for recipe in recipes}

    def item(self, nickname: str) -> dict[str, str]:
        return self.gamedata.resolve(nickname)

    def public_recipes(self, inventory: dict[str, int] | None = None) -> list[dict[str, Any]]:
        inventory = inventory or {}
        result = []
        for recipe in self.recipes:
            result.append({
                "id": recipe.id,
                "result": self.item(recipe.result),
                "amount": recipe.amount,
                "station": recipe.station,
                "tier": recipe.tier,
                "description": recipe.description,
                "ingredients": [
                    {"item": self.item(nickname), "amount": amount, "available": inventory.get(nickname, 0)}
                    for nickname, amount in recipe.ingredients.items()
                ],
                "can_craft": self.can_craft(recipe, inventory),
            })
        return result

    @staticmethod
    def can_craft(recipe: CraftingRecipe, inventory: dict[str, int]) -> bool:
        return all(inventory.get(nickname, 0) >= amount for nickname, amount in recipe.ingredients.items())

    def craft(self, character_path: Path, recipe_id: str) -> tuple[bool, str]:
        recipe = self.by_id.get(recipe_id)
        if not recipe:
            return False, "Рецепт не найден."
        inventory = read_cargo_inventory(character_path, self.gamedata)
        if not self.can_craft(recipe, inventory):
            missing = []
            for nickname, amount in recipe.ingredients.items():
                available = inventory.get(nickname, 0)
                if available < amount:
                    item = self.item(nickname)
                    missing.append(f"{item['name']}: нужно {amount}, есть {available}")
            return False, "Недостаточно ресурсов: " + "; ".join(missing)
        changes = {nickname: -amount for nickname, amount in recipe.ingredients.items()}
        changes[recipe.result] = changes.get(recipe.result, 0) + recipe.amount
        try:
            update_character_cargo(character_path, changes)
        except ValueError as exc:
            return False, str(exc)
        item = self.item(recipe.result)
        return True, f"Создано: {item['name']} x{recipe.amount}."


def cargo_keys(nickname: str, gamedata: GameData | None = None) -> set[str]:
    keys = {nickname, nickname_hash(nickname)}
    if gamedata:
        item = gamedata.resolve(nickname)
        keys.update({item["code"], item["nickname"], nickname_hash(item["nickname"])})
    return {key for key in keys if key}


def read_cargo_inventory(character_path: Path, gamedata: GameData | None = None) -> dict[str, int]:
    inventory: dict[str, int] = {}
    for raw_line in read_text(character_path).splitlines():
        line = raw_line.strip()
        if not re.match(r"^cargo\s*=", line, re.I):
            continue
        value = line.split("=", 1)[1].strip()
        parts = split_csv(value)
        if not parts:
            continue
        item = gamedata.resolve(parts[0])["nickname"] if gamedata else parts[0]
        amount = int(float(parts[1])) if len(parts) > 1 and parts[1] else 1
        inventory[item] = inventory.get(item, 0) + max(0, amount)
    return inventory


def update_character_cargo(character_path: Path, changes: dict[str, int]) -> None:
    pending = {nickname: int(delta) for nickname, delta in changes.items() if int(delta)}
    if not pending:
        return
    lines = read_text(character_path).splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not re.match(r"^\s*cargo\s*=", line, re.I):
            continue
        prefix, value = line.split("=", 1)
        parts = split_csv(value)
        if not parts:
            continue
        nickname = parts[0]
        for target in list(pending):
            if nickname not in cargo_keys(target):
                continue
            current = int(float(parts[1])) if len(parts) > 1 and parts[1] else 1
            updated = current + pending[target]
            pending[target] = 0
            if updated <= 0:
                lines[index] = ""
            else:
                while len(parts) < 5:
                    parts.append("")
                parts[0] = target
                parts[1] = str(updated)
                ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                lines[index] = f"{prefix.strip()} = {', '.join(parts)}{ending}"
            break
    insert_at = next((i + 1 for i, line in reversed(list(enumerate(lines))) if re.match(r"^\s*cargo\s*=", line, re.I)), len(lines))
    additions = []
    for nickname, delta in pending.items():
        if delta > 0:
            additions.append(f"cargo = {nickname_hash(nickname)}, {delta}, , , 0\n")
        elif delta < 0:
            raise ValueError(f"Not enough cargo to remove {nickname}: {-delta}")
    if additions:
        lines[insert_at:insert_at] = additions
    character_path.write_text("".join(lines), encoding="utf-8")
