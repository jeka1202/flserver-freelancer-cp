from pathlib import Path

root = Path(__file__).resolve().parent
repo_path = root / "fl_panel" / "repository.py"

if not repo_path.exists():
    raise SystemExit(f"Не найден файл: {repo_path}")

text = repo_path.read_text(encoding="utf-8")

old_deposit = """        if action == "deposit":
            if character_money < amount:
                return False, "На игровом счёте персонажа недостаточно средств для зачисления в банк."
            write_character_money(character_path, character_money - amount)
            write_bank_balance(account_path, bank_money + amount)
            self.reload()
            return True, f"{money(amount)} кредитов переведено с персонажа в bank.ini."
"""

new_deposit = """        if action == "deposit":
            if character_money < amount:
                return False, "На игровом счёте персонажа недостаточно средств для зачисления в банк."

            new_character_money = character_money - amount
            new_bank_money = bank_money + amount

            write_character_money(character_path, new_character_money)
            write_bank_balance(account_path, new_bank_money)

            account = self.by_id.get(account_id.lower())
            if account:
                for current_character in account["characters"]:
                    if current_character["file"] == character_file:
                        self.set_character_money(account, current_character, new_character_money)
                        break
                self.set_account_bank(account, new_bank_money)

            return True, f"{money(amount)} кредитов переведено с персонажа в bank.ini."
"""

old_withdraw = """        if action == "withdraw":
            if bank_money < amount:
                return False, "В bank.ini недостаточно средств для вывода персонажу."
            write_bank_balance(account_path, bank_money - amount)
            write_character_money(character_path, character_money + amount)
            self.reload()
            return True, f"{money(amount)} кредитов выведено из bank.ini персонажу."
"""

new_withdraw = """        if action == "withdraw":
            if bank_money < amount:
                return False, "В bank.ini недостаточно средств для вывода персонажу."

            new_bank_money = bank_money - amount
            new_character_money = character_money + amount

            write_bank_balance(account_path, new_bank_money)
            write_character_money(character_path, new_character_money)

            account = self.by_id.get(account_id.lower())
            if account:
                for current_character in account["characters"]:
                    if current_character["file"] == character_file:
                        self.set_character_money(account, current_character, new_character_money)
                        break
                self.set_account_bank(account, new_bank_money)

            return True, f"{money(amount)} кредитов выведено из bank.ini персонажу."
"""

old_transfer = """        write_character_money(sender_path, sender_money - debit_from_character)
        if debit_from_bank:
            write_bank_balance(sender_account_path, sender_bank - debit_from_bank)
        write_character_money(target_path, target_money + amount)
        self.reload()
        details = f"списано {money(debit_from_character)} с персонажа"
"""

new_transfer = """        new_sender_money = sender_money - debit_from_character
        new_sender_bank = sender_bank - debit_from_bank
        new_target_money = target_money + amount

        write_character_money(sender_path, new_sender_money)
        if debit_from_bank:
            write_bank_balance(sender_account_path, new_sender_bank)
        write_character_money(target_path, new_target_money)

        sender_account = self.by_id.get(sender_account_id.lower())
        if sender_account:
            for sender_character in sender_account["characters"]:
                if sender_character["file"] == sender_file:
                    self.set_character_money(sender_account, sender_character, new_sender_money)
                    break
            if debit_from_bank:
                self.set_account_bank(sender_account, new_sender_bank)

        self.set_character_money(target_account, target_character, new_target_money)

        details = f"списано {money(debit_from_character)} с персонажа"
"""

replacements = [
    (old_deposit, new_deposit, "deposit block"),
    (old_withdraw, new_withdraw, "withdraw block"),
    (old_transfer, new_transfer, "transfer block"),
]

for old, new, name in replacements:
    if old not in text:
        print(f"WARNING: не найден блок для замены: {name}")
    else:
        text = text.replace(old, new, 1)
        print(f"OK: заменён {name}")

repo_path.write_text(text, encoding="utf-8")

print("Готово. Теперь перезапусти панель:")
print("py .\\account_panel.py")
