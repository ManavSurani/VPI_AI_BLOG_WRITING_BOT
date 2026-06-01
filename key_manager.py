"""
key_manager.py — API key rotation with cooldown tracking.
Handles: single key, no second key, invalid keys, empty keys, placeholders.
Does NOT touch any blog logic.
"""

import os, json, time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

STATUS_FILE      = "key_status.json"
COOLDOWN_MINUTES = 61


def is_valid_key(key):
    if not key:
        return False, "Key is empty"
    key = key.strip()
    if len(key) < 10:
        return False, f"Key too short ({len(key)} chars)"
    if key in ["your_key_here", "paste_your_key", "xxx", "YOUR_API_KEY"]:
        return False, "Key is still a placeholder"
    if " " in key:
        return False, "Key contains spaces — copy it again carefully"
    if key.startswith("your_") or key.startswith("paste_"):
        return False, "Key looks like placeholder text"
    return True, "OK"


def load_keys(prefix):
    raw_keys = []
    skipped  = []

    single = os.environ.get(prefix, "").strip()
    if single:
        raw_keys.append(("legacy", single))

    i = 1
    while True:
        key = os.environ.get(f"{prefix}_{i}", "").strip()
        if not key:
            break
        raw_keys.append((f"{prefix}_{i}", key))
        i += 1

    valid_keys = []
    for name, key in raw_keys:
        ok, reason = is_valid_key(key)
        if ok:
            if key not in valid_keys:
                valid_keys.append(key)
        else:
            skipped.append((name, reason))

    for name, reason in skipped:
        print(f"  Warning: Skipping {name} — {reason}")

    return valid_keys


def load_status():
    if not os.path.exists(STATUS_FILE):
        return {}
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_status(status):
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"  Warning: Could not save key status: {e}")


class KeyManager:
    def __init__(self, prefix):
        self.prefix   = prefix
        self.status   = load_status()
        self.bad_keys = set()
        self.idx      = 0

        all_keys = load_keys(prefix)

        bad_from_file = self.status.get(f"{prefix}_bad_keys", [])
        self.keys = [k for k in all_keys if k not in bad_from_file]

        if not self.keys:
            if all_keys:
                print(f"\n  All {prefix} keys were marked invalid previously.")
                print(f"  Clearing history and retrying...")
                self.status.pop(f"{prefix}_bad_keys", None)
                save_status(self.status)
                self.keys = all_keys
            else:
                raise ValueError(
                    f"\n  No valid {prefix} keys found in .env\n"
                    f"  Add at least: {prefix}_1=your_key_here"
                )

        self.idx = self._find_best_key()
        self._print_status()

    def _key_id(self, idx):
        return f"{self.prefix}_{idx}"

    def _is_on_cooldown(self, idx):
        kid = self._key_id(idx)
        if kid not in self.status:
            return False
        try:
            exhausted_at = datetime.fromisoformat(self.status[kid]["exhausted_at"])
            return datetime.now() < exhausted_at + timedelta(minutes=COOLDOWN_MINUTES)
        except Exception:
            return False

    def _cooldown_remaining(self, idx):
        kid = self._key_id(idx)
        if kid not in self.status:
            return 0
        try:
            exhausted_at = datetime.fromisoformat(self.status[kid]["exhausted_at"])
            cooldown_end = exhausted_at + timedelta(minutes=COOLDOWN_MINUTES)
            return max(0, (cooldown_end - datetime.now()).total_seconds())
        except Exception:
            return 0

    def _find_best_key(self):
        best_idx       = 0
        best_remaining = float("inf")
        for i in range(len(self.keys)):
            if self.keys[i] in self.bad_keys:
                continue
            remaining = self._cooldown_remaining(i)
            if remaining == 0:
                return i
            if remaining < best_remaining:
                best_remaining = remaining
                best_idx       = i
        return best_idx

    def _mark_exhausted(self, idx):
        kid = self._key_id(idx)
        self.status[kid] = {
            "exhausted_at": datetime.now().isoformat(),
            "key_index": idx
        }
        save_status(self.status)

    def _mark_bad_key(self, idx):
        bad_key = self.keys[idx]
        self.bad_keys.add(bad_key)
        bad_list = self.status.get(f"{self.prefix}_bad_keys", [])
        if bad_key not in bad_list:
            bad_list.append(bad_key)
        self.status[f"{self.prefix}_bad_keys"] = bad_list
        save_status(self.status)
        print(f"  Key {idx+1} marked invalid — skipped in future runs")

    def _print_status(self):
        print(f"\n  {self.prefix} — {len(self.keys)} key(s) loaded:")
        for i, key in enumerate(self.keys):
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
            active = " <- ACTIVE" if i == self.idx else ""
            if key in self.bad_keys:
                print(f"    Key {i+1}: Invalid (skipped){active}")
            elif self._is_on_cooldown(i):
                mins = int(self._cooldown_remaining(i) / 60)
                print(f"    Key {i+1}: Cooldown ({mins} min left) [{masked}]{active}")
            else:
                print(f"    Key {i+1}: Ready [{masked}]{active}")

    def current_key(self):
        return self.keys[self.idx]

    def rotate(self, reason="rate_limit"):
        if reason == "invalid":
            print(f"\n  {self.prefix} Key {self.idx+1} is invalid (wrong or deleted)")
            self._mark_bad_key(self.idx)
        else:
            print(f"\n  {self.prefix} Key {self.idx+1} rate limited — rotating...")
            self._mark_exhausted(self.idx)

        good_keys = [
            i for i in range(len(self.keys))
            if self.keys[i] not in self.bad_keys
        ]

        if not good_keys:
            raise RuntimeError(
                f"\n  All {self.prefix} keys are invalid or exhausted.\n"
                f"  Add new keys to .env:\n"
                f"  {self.prefix}_1=new_key_here"
            )

        next_idx  = self._find_best_key()
        remaining = self._cooldown_remaining(next_idx)

        if remaining > 0 and self.keys[next_idx] not in self.bad_keys:
            wait_mins = int(remaining / 60) + 1
            wait_secs = int(remaining) + 5
            print(f"  All keys on cooldown. Key {next_idx+1} resets in {wait_mins} min — waiting...")
            time.sleep(wait_secs)

        self.idx = next_idx
        print(f"  Switched to {self.prefix} Key {self.idx+1}")
        return self.current_key()
