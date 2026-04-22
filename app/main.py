"""
Entry point. Loads config (or falls back to sleep-only mode) and starts
the pet + (optional) Gmail monitor.

Supports running both from source AND as a PyInstaller-bundled .exe:
- assets are looked up inside the bundle (sys._MEIPASS) when frozen
- config.json lives in %APPDATA%\\TotoAgent\\ so it survives reinstalls
"""
import json
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from pet import PetWindow
from mail_monitor import MailMonitor


def resource_path(rel: str) -> Path:
    """Path to a bundled resource (dev or PyInstaller frozen)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).parent / rel


def user_config_dir() -> Path:
    """Writable per-user directory that persists across upgrades."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "TotoAgent"
    else:
        base = Path.home() / ".config" / "bulldog-pet"
    base.mkdir(parents=True, exist_ok=True)
    return base


ASSETS = resource_path("assets_processed")
CONFIG_DIR = user_config_dir()
CONFIG = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[warn] config.json invalid ({e}); running in sleep-only mode")
            return {}
    # Seed an example config the user can later edit.
    example = resource_path("config.example.json")
    if example.exists():
        try:
            (CONFIG_DIR / "config.example.json").write_text(
                example.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    print(f"[info] no config at {CONFIG} — sleep-only mode. "
          f"Use tray -> 'Configure Gmail' to set up.")
    return {}


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray keeps it alive

    cfg = load_config()
    pet = PetWindow(assets_dir=ASSETS, cfg=cfg, config_dir=CONFIG_DIR)
    pet.show()

    # Hold the monitor in a mutable so the restart closure can swap it.
    state = {"monitor": None}

    def restart_monitor(new_cfg: dict):
        if state["monitor"]:
            state["monitor"].stop()
            state["monitor"] = None
        g = (new_cfg or {}).get("gmail", {}) or {}
        if not g.get("enabled"):
            print("[info] Gmail disabled — use tray 'Test: bark + run' to trigger.")
            return
        try:
            m = MailMonitor(g)
            m.new_mail.connect(pet.on_new_mail)
            m.start()
            state["monitor"] = m
            print(f"[info] Gmail monitor started for {g.get('username')}")
        except KeyError as e:
            print(f"[error] gmail config missing key: {e}")
        except Exception as e:
            print(f"[error] could not start monitor: {e}")

    pet.configSaved.connect(restart_monitor)
    restart_monitor(cfg)

    rc = app.exec()
    if state["monitor"]:
        state["monitor"].stop()
    sys.exit(rc)


if __name__ == "__main__":
    main()
