from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Dict

SETTINGS_FILENAME = "settings.dat"
APP_SECRET = "KIwcVIWqzrPoBzrlTdN1lvnTcpX7sikf"  # можете заменить, но тогда старые settings.dat не прочитаются

def exe_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

SETTINGS_PATH = exe_dir() / SETTINGS_FILENAME

def _is_windows() -> bool:
    import platform
    return platform.system().lower().startswith("win")

def _dpapi_protect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    CryptProtectData = ctypes.windll.crypt32.CryptProtectData
    CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    CryptProtectData.restype = wintypes.BOOL

    in_blob = DATA_BLOB(cbData=len(data), pbData=ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()

    if not CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise RuntimeError("DPAPI protect failed")

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
    CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    CryptUnprotectData.restype = wintypes.BOOL

    in_blob = DATA_BLOB(cbData=len(data), pbData=ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()

    if not CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise RuntimeError("DPAPI unprotect failed")

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

def _fallback_key() -> bytes:
    return hashlib.sha256(APP_SECRET.encode("utf-8")).digest()

def _fallback_encrypt(data: bytes) -> bytes:
    key = _fallback_key()
    mac = hmac.new(key, data, hashlib.sha256).digest()
    return base64.b64encode(mac + data)

def _fallback_decrypt(packed: bytes) -> bytes:
    raw = base64.b64decode(packed)
    key = _fallback_key()
    mac = raw[:32]
    data = raw[32:]
    if not hmac.compare_digest(mac, hmac.new(key, data, hashlib.sha256).digest()):
        raise RuntimeError("Settings integrity check failed")
    return data

def _encrypt_dict(d: Dict[str, Any]) -> bytes:
    data = json.dumps(d, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if _is_windows():
        try:
            return b"WDP1" + _dpapi_protect(data)
        except Exception:
            pass
    return b"FBK1" + _fallback_encrypt(data)

def _decrypt_dict(blob: bytes) -> Dict[str, Any]:
    if not blob:
        return {}
    try:
        if blob.startswith(b"WDP1"):
            return json.loads(_dpapi_unprotect(blob[4:]).decode("utf-8"))
        if blob.startswith(b"FBK1"):
            return json.loads(_fallback_decrypt(blob[4:]).decode("utf-8"))
        return json.loads(blob.decode("utf-8", errors="replace"))
    except Exception:
        return {}

_defaults: Dict[str, Dict[str, Any]] = {
    "DB": {
        "provider": "postgres",
        "database_url": "postgresql://sport_app_user:CHANGE_ME@127.0.0.1:5432/sport_schedule?sslmode=disable",
        "sslmode": "disable",
    }
}

_store: Dict[str, Dict[str, Any]] = {}

def _ensure_sections():
    for sec, vals in _defaults.items():
        _store.setdefault(sec, {})
        for k, v in vals.items():
            if k not in _store[sec]:
                _store[sec][k] = v

def load_settings():
    global _store
    if SETTINGS_PATH.exists():
        try:
            _store = _decrypt_dict(SETTINGS_PATH.read_bytes())
            if not isinstance(_store, dict):
                _store = {}
        except Exception:
            _store = {}
    else:
        _store = {}
    _ensure_sections()
    if not SETTINGS_PATH.exists():
        save_settings()

def save_settings():
    _ensure_sections()
    SETTINGS_PATH.write_bytes(_encrypt_dict(_store))

def ensure_config():
    load_settings()

def get_database_url() -> str:
    ensure_config()
    return str(_store["DB"].get("database_url", ""))

def set_database_url(url: str):
    ensure_config()
    _store["DB"]["database_url"] = (url or "").strip()
    save_settings()
