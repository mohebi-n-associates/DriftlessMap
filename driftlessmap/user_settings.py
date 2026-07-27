import json
import os
from pathlib import Path
import sys
import tempfile


SETTINGS_SCHEMA_VERSION = 1


def _platform_config_root():
    if sys.platform == "win32":
        return Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def user_config_directory():
    override = os.environ.get("DRIFTLESSMAP_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    legacy_override = os.environ.get("HERBS_CONFIG_DIR")
    if legacy_override:
        return Path(legacy_override).expanduser()
    return _platform_config_root() / "DriftlessMap"


def settings_path():
    return user_config_directory() / "settings.json"


def _legacy_settings_path():
    if os.environ.get("DRIFTLESSMAP_CONFIG_DIR") or os.environ.get(
        "HERBS_CONFIG_DIR"
    ):
        return None
    return _platform_config_root() / "HERBS" / "settings.json"


def load_last_atlas_path():
    current_path = settings_path()
    candidates = [current_path]
    legacy_path = _legacy_settings_path()
    if not current_path.exists() and legacy_path is not None:
        candidates.append(legacy_path)

    settings = None
    for candidate in candidates:
        try:
            with candidate.open(encoding="utf-8") as handle:
                settings = json.load(handle)
            break
        except (OSError, ValueError, TypeError):
            continue
    if settings is None:
        return None
    if settings.get("schema_version") != SETTINGS_SCHEMA_VERSION:
        return None
    atlas_path = settings.get("last_atlas_path")
    if not isinstance(atlas_path, str) or not atlas_path:
        return None
    return atlas_path


def save_last_atlas_path(atlas_path):
    atlas_path = os.fspath(atlas_path)
    if not atlas_path:
        raise ValueError("Atlas path must not be empty.")

    destination = settings_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    settings = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "last_atlas_path": atlas_path,
    }
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".settings-", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(settings, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
