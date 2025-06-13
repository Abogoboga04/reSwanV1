import json
import os
from datetime import datetime

FILE_PATH = "data/level_data.json"

# Default values yang ingin ditambahkan jika belum ada
DEFAULT_FIELDS = {
    "exp": 0,
    "level": 0,
    "weekly_exp": 0,
    "badges": [],
    "booster": {},
    "last_active": None,
    "last_completed_quest": None,
    "last_exp_purchase": None,
    "purchased_roles": []
}

def fix_level_data(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} tidak ditemukan.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = False
    for guild_id, users in data.items():
        for user_id, user_data in users.items():
            for key, default_value in DEFAULT_FIELDS.items():
                if key not in user_data:
                    user_data[key] = default_value
                    print(f"[UPDATE] Menambahkan '{key}' ke user {user_id} di guild {guild_id}")
                    updated = True

    if updated:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print("✅ Semua field yang hilang berhasil ditambahkan.")
    else:
        print("✅ Semua data sudah lengkap, tidak ada perubahan.")

if __name__ == "__main__":
    fix_level_data(FILE_PATH)
