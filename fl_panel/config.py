from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = ROOT / "Accts" / "MultiPlayer"
IONCROSS_DIR = ROOT / "IONCROSS"
STATIC_DIR = Path(__file__).resolve().parent / "static"
BANK_SECTION = "Bank"
BANK_KEY = "balance"

DATA_FILES = {
    "ammo": "GAMEDATA_ammo.txt",
    "bases": "GAMEDATA_bases.txt",
    "cargo": "GAMEDATA_cargo.txt",
    "countermeasures": "GAMEDATA_countermeasures.txt",
    "engines": "GAMEDATA_engines.txt",
    "factions": "GAMEDATA_factions.txt",
    "guns": "GAMEDATA_guns.txt",
    "lights": "GAMEDATA_lights.txt",
    "mapinfo": "GAMEDATA_mapinfo.txt",
    "mines": "GAMEDATA_mines.txt",
    "misc_equipment": "GAMEDATA_miscequipment.txt",
    "power_generators": "GAMEDATA_powergenerators.txt",
    "projectiles": "GAMEDATA_projectiles.txt",
    "scanners": "GAMEDATA_scanners.txt",
    "shields": "GAMEDATA_shields.txt",
    "ships": "GAMEDATA_ships.txt",
    "systems": "GAMEDATA_systems.txt",
    "thrusters": "GAMEDATA_thrusters.txt",
    "tractorbeams": "GAMEDATA_tractorbeams.txt",
    "turrets": "GAMEDATA_turrets.txt",
}

CATEGORY_LABELS = {
    "ammo": "Боеприпасы",
    "bases": "Базы",
    "cargo": "Груз/товары",
    "countermeasures": "Контрмеры",
    "engines": "Двигатели",
    "factions": "Фракции",
    "guns": "Оружие",
    "lights": "Огни",
    "mapinfo": "Карта",
    "mines": "Мины",
    "misc_equipment": "Оборудование",
    "power_generators": "Генераторы",
    "projectiles": "Снаряды",
    "scanners": "Сканеры",
    "shields": "Щиты",
    "ships": "Корабли",
    "systems": "Системы",
    "thrusters": "Форсаж",
    "tractorbeams": "Тракторы",
    "turrets": "Турели",
    "unknown": "Неизвестно",
}

VISIT_TYPES = {
    "1": "система",
    "17": "прыжковая дыра/ворота",
    "33": "объект карты",
    "41": "база/объект",
    "45": "торговая линия/зона",
    "65": "информационная отметка",
}
