from __future__ import annotations

import json
import os
import re
import shutil
import uuid
import cgi
import io
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from html import unescape
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_SOURCE_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_SOURCE_DIR / "dist"
FRONTEND_DIR = FRONTEND_DIST_DIR if FRONTEND_DIST_DIR.exists() else FRONTEND_SOURCE_DIR
ENV_PATH = ROOT_DIR / ".env"
RAG_DIR = ROOT_DIR / "rag_store"
RAG_FILES_DIR = RAG_DIR / "files"
RAG_TEXT_DIR = RAG_DIR / "texts"
RAG_INDEX_PATH = RAG_DIR / "index.json"
PATIENT_DIR = ROOT_DIR / "patient_store"
PATIENT_DICOM_DIR = PATIENT_DIR / "dicom"
PATIENT_INDEX_PATH = PATIENT_DIR / "index.json"
PATIENT_NII_DIR = PATIENT_DIR / "nii"
PATIENT_NII_INDEX_PATH = PATIENT_DIR / "nii_index.json"

MODELS = [
    "qwen3.7-max",
    "gemini-3.5-flash",
    "deepseek-v4-pro",
    "kimi-k2.6",
    "glm-5",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "查询指定时区的当前日期和时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区名称，例如 Asia/Shanghai 或 America/New_York。",
                    }
                },
                "required": ["timezone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市或地点名称，例如 Beijing、Shanghai、New York。",
                    }
                },
                "required": ["location"],
            },
        },
    },
]

WEATHER_CODES = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    95: "雷暴",
}

SUPPORTED_RAG_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".doc"}
SUPPORTED_DICOM_EXTENSIONS = {".dcm", ".dicom", ""}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def ensure_rag_store() -> None:
    RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)
    RAG_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    if not RAG_INDEX_PATH.exists():
        RAG_INDEX_PATH.write_text("[]", encoding="utf-8")


def load_rag_index() -> list[dict[str, Any]]:
    ensure_rag_store()
    try:
        data = json.loads(RAG_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = []
    return data if isinstance(data, list) else []


def save_rag_index(items: list[dict[str, Any]]) -> None:
    ensure_rag_store()
    RAG_INDEX_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_patient_store() -> None:
    PATIENT_DICOM_DIR.mkdir(parents=True, exist_ok=True)
    if not PATIENT_INDEX_PATH.exists():
        PATIENT_INDEX_PATH.write_text("[]", encoding="utf-8")


def load_patient_index() -> list[dict[str, Any]]:
    ensure_patient_store()
    try:
        data = json.loads(PATIENT_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = []
    return data if isinstance(data, list) else []


def save_patient_index(items: list[dict[str, Any]]) -> None:
    ensure_patient_store()
    PATIENT_INDEX_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_nii_store() -> None:
    PATIENT_NII_DIR.mkdir(parents=True, exist_ok=True)
    if not PATIENT_NII_INDEX_PATH.exists():
        PATIENT_NII_INDEX_PATH.write_text("[]", encoding="utf-8")


def load_nii_index() -> list[dict[str, Any]]:
    ensure_nii_store()
    try:
        data = json.loads(PATIENT_NII_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = []
    return data if isinstance(data, list) else []


def save_nii_index(items: list[dict[str, Any]]) -> None:
    ensure_nii_store()
    PATIENT_NII_INDEX_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def api_base_url() -> str:
    base_url = os.getenv("BASE_URL", "https://api.openai-proxy.org").rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def api_key() -> str:
    return (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("API_KEY")
        or os.getenv("KEY")
        or ""
    )


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def json_request(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            **(headers or {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def estimate_tokens_from_text(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, (ascii_chars // 4) + (non_ascii_chars // 2))


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", Path(name).name, flags=re.UNICODE)
    return cleaned.strip("._") or "uploaded_file"
