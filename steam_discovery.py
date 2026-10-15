"""Find and validate a local Dota 2 game directory on Windows."""
from pathlib import Path
import re
import os


def _steam_roots():
    roots = set()
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            value, _ = winreg.QueryValueEx(handle, name)
                            if value:
                                roots.add(Path(os.path.expandvars(value)))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    for value in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                  os.environ.get("LOCALAPPDATA")):
        if value:
            root = Path(value)
            roots.update((root / "Steam", root / "Programs" / "Steam"))
    return sorted((p for p in roots if p.is_dir()), key=lambda p: str(p).casefold())


def _unescape_vdf_path(value):
    return value.replace(r"\\", "\\").replace(r"\"", '"')


def _libraries(steam_root):
    result = {steam_root}
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        try:
            text = vdf.read_text("utf-8-sig", errors="replace")
            for raw in re.findall(r'"path"\s*"((?:\\.|[^"\\])*)"', text, re.I):
                result.add(Path(_unescape_vdf_path(raw)))
            # Older libraryfolders.vdf files use numbered string values.
            if len(result) == 1:
                body = re.search(r'"libraryfolders"\s*\{(.*)\}', text, re.I | re.S)
                if body:
                    for raw in re.findall(r'"\d+"\s*"((?:\\.|[^"\\])*)"', body.group(1)):
                        result.add(Path(_unescape_vdf_path(raw)))
        except OSError:
            pass
    return result


def normalize_game_path(path):
    """Accept either the game's ``game`` folder or its install root."""
    candidate = Path(path).expanduser().absolute()
    if candidate.name.casefold() != "game":
        if (candidate / "game").is_dir():
            candidate = candidate / "game"
    if not (candidate / "dota" / "gameinfo.gi").is_file():
        raise ValueError("Selecione a pasta game do Dota 2 (a que contém dota\\gameinfo.gi).")
    if not (candidate / "dota" / "maps" / "dota.vpk").is_file():
        raise ValueError("Esta pasta não contém os mapas oficiais do Dota 2.")
    if not (candidate / "dota" / "cfg" / "boot.vcfg").is_file():
        raise ValueError("Configuração de instalação do Dota não encontrada nesta pasta.")
    return candidate.resolve()


def find_dota_installations():
    found = {}
    for steam in _steam_roots():
        for library in _libraries(steam):
            game = library / "steamapps" / "common" / "dota 2 beta" / "game"
            try:
                valid = normalize_game_path(game)
                found[str(valid).casefold()] = valid
            except (OSError, ValueError):
                continue
    return sorted(found.values(), key=lambda p: str(p).casefold())
