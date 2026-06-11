from __future__ import annotations

import io
import json
import re
import shutil
import urllib.parse
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from config import (
    PATIENT_DICOM_DIR,
    SUPPORTED_DICOM_EXTENSIONS,
    load_patient_index,
    save_patient_index,
    ensure_patient_store,
    safe_filename,
)

def normalize_dicom_value(value: Any, max_length: int = 240) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value[:64].hex(" ")
    elif isinstance(value, (list, tuple)):
        text = ", ".join(normalize_dicom_value(item, max_length=80) for item in value)
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        return f"{text[:max_length]}..."
    return text


def parse_dicom_header(path: Path) -> dict[str, Any]:
    try:
        import pydicom
    except ImportError as exc:
        raise ValueError("缺少 pydicom，无法解析 DICOM 文件。") from exc

    dataset = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
    fields = []
    for element in dataset.iterall():
        if element.tag.group == 0x7FE0:
            continue
        fields.append(
            {
                "tag": str(element.tag),
                "keyword": element.keyword or "",
                "name": element.name,
                "vr": element.VR,
                "value": normalize_dicom_value(element.value),
            }
        )

    summary_keys = {
        "patient_name": "PatientName",
        "patient_id": "PatientID",
        "patient_sex": "PatientSex",
        "patient_age": "PatientAge",
        "study_date": "StudyDate",
        "study_time": "StudyTime",
        "modality": "Modality",
        "study_description": "StudyDescription",
        "series_description": "SeriesDescription",
        "body_part": "BodyPartExamined",
        "institution": "InstitutionName",
        "manufacturer": "Manufacturer",
    }
    summary = {
        output_key: normalize_dicom_value(getattr(dataset, dicom_key, ""))
        for output_key, dicom_key in summary_keys.items()
    }
    return {"summary": summary, "fields": fields}


def safe_relative_upload_path(filename: str, fallback: str) -> Path:
    raw_parts = PurePosixPath(str(filename).replace("\\", "/")).parts
    safe_parts = [safe_filename(part) for part in raw_parts if part not in {"", ".", "..", "/"}]
    if not safe_parts:
        safe_parts = [fallback]
    return Path(*safe_parts)


def save_uploaded_dicom_folder(uploads: list[Any]) -> dict[str, Any]:
    ensure_patient_store()
    group_id = uuid.uuid4().hex
    group_dir = PATIENT_DICOM_DIR / group_id
    group_dir.mkdir(parents=True, exist_ok=True)

    parsed_files = []
    errors = []
    total_size = 0
    folder_name = ""

    for index, upload in enumerate(uploads, start=1):
        filename = getattr(upload, "filename", "") or f"dicom-{index}.dcm"
        relative_path = safe_relative_upload_path(filename, f"dicom-{index}.dcm")
        if not folder_name and len(relative_path.parts) > 1:
            folder_name = relative_path.parts[0]
        extension = relative_path.suffix.lower()
        if extension not in SUPPORTED_DICOM_EXTENSIONS:
            errors.append({"filename": filename, "error": "不是 DICOM 文件扩展名。"})
            continue

        target_path = group_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)

        try:
            parsed = parse_dicom_header(target_path)
        except Exception as exc:  # noqa: BLE001
            target_path.unlink(missing_ok=True)
            errors.append({"filename": filename, "error": str(exc)})
            continue

        rel_text = relative_path.as_posix()
        fields = [{**field, "file": rel_text} for field in parsed["fields"]]
        parsed_files.append(
            {
                "filename": rel_text,
                "size": target_path.stat().st_size,
                "summary": parsed["summary"],
                "fields": fields,
            }
        )
        total_size += target_path.stat().st_size

    if not parsed_files:
        shutil.rmtree(group_dir, ignore_errors=True)
        detail = errors[0]["error"] if errors else "没有可解析的 DICOM 文件。"
        raise ValueError(detail)

    first = parsed_files[0]
    first_summary = first["summary"]
    fields = []
    for parsed_file in parsed_files:
        fields.extend(parsed_file["fields"])

    item = {
        "id": group_id,
        "filename": folder_name or Path(first["filename"]).parent.name or first["filename"],
        "stored_dir": group_id,
        "size": total_size,
        "file_count": len(parsed_files),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        **first_summary,
        "dicom_files": [
            {"filename": parsed_file["filename"], "size": parsed_file["size"]}
            for parsed_file in parsed_files
        ],
        "fields": fields,
        "errors": errors,
    }
    items = load_patient_index()
    items.append(item)
    save_patient_index(items)
    return item


def save_uploaded_dicom_file(filename: str, source: Any) -> dict[str, Any]:
    ensure_patient_store()
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_DICOM_EXTENSIONS:
        raise ValueError("仅支持 .dcm、.dicom 或无扩展名的 DICOM 文件。")

    file_id = uuid.uuid4().hex
    safe_name = Path(filename).name or f"{file_id}.dcm"
    stored_name = f"{file_id}{extension or '.dcm'}"
    file_path = PATIENT_DICOM_DIR / stored_name
    with file_path.open("wb") as target:
        shutil.copyfileobj(source, target)

    parsed = parse_dicom_header(file_path)
    item = {
        "id": file_id,
        "filename": safe_name,
        "stored_name": stored_name,
        "size": file_path.stat().st_size,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        **parsed["summary"],
        "fields": parsed["fields"],
    }
    items = load_patient_index()
    items.append(item)
    save_patient_index(items)
    return item


def delete_patient_dicom(file_id: str) -> dict[str, Any]:
    items = load_patient_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("病人数据不存在。")
    stored_dir = item.get("stored_dir", "")
    if stored_dir:
        shutil.rmtree(PATIENT_DICOM_DIR / stored_dir, ignore_errors=True)
    stored_name = item.get("stored_name", "")
    if stored_name:
        (PATIENT_DICOM_DIR / stored_name).unlink(missing_ok=True)
    save_patient_index([entry for entry in items if entry.get("id") != file_id])
    return item


def update_patient_dicom(file_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    editable_keys = {
        "filename",
        "patient_name",
        "patient_id",
        "patient_sex",
        "patient_age",
        "study_date",
        "study_time",
        "modality",
        "body_part",
        "study_description",
        "series_description",
        "institution",
        "manufacturer",
    }
    items = load_patient_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("病人数据不存在。")
    for key in editable_keys:
        if key in updates:
            item[key] = str(updates.get(key, "")).strip()
    item["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_patient_index(items)
    return item


def get_patient_dicom(file_id: str) -> dict[str, Any]:
    item = next((entry for entry in load_patient_index() if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("病人数据不存在。")
    return item


def patient_dicom_path(item: dict[str, Any], relative_filename: str) -> Path:
    allowed = {entry.get("filename") for entry in item.get("dicom_files", [])}
    if allowed and relative_filename not in allowed:
        raise ValueError("DICOM 文件不属于该患者。")
    stored_dir = item.get("stored_dir", "")
    if stored_dir:
        path = (PATIENT_DICOM_DIR / stored_dir / Path(relative_filename)).resolve()
        root = (PATIENT_DICOM_DIR / stored_dir).resolve()
        if root not in path.parents and path != root:
            raise ValueError("DICOM 文件路径非法。")
        return path
    stored_name = item.get("stored_name", "")
    if stored_name and (not relative_filename or relative_filename == item.get("filename")):
        return PATIENT_DICOM_DIR / stored_name
    raise ValueError("DICOM 文件不存在。")


def list_patient_dicom_images(file_id: str) -> dict[str, Any]:
    item = get_patient_dicom(file_id)
    files = item.get("dicom_files") or [{"filename": item.get("filename", ""), "size": item.get("size", 0)}]
    images = []
    for index, entry in enumerate(files):
        filename = entry.get("filename", "")
        if not filename:
            continue
        images.append(
            {
                "index": index,
                "filename": filename,
                "size": entry.get("size", 0),
                "image_url": f"/api/patients/dicom/{urllib.parse.quote(file_id)}/image?file={urllib.parse.quote(filename)}",
            }
        )
    return {"patient": item, "images": images}


def optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_dicom_png(
    file_id: str,
    relative_filename: str,
    window_width: float | None = None,
    window_center: float | None = None,
    contrast: float = 1,
    brightness: float = 0,
) -> bytes:
    try:
        import numpy as np
        import pydicom
        from PIL import Image
    except ImportError as exc:
        raise ValueError("缺少 numpy、Pillow 或 pydicom，无法显示 DICOM 图像。") from exc

    item = get_patient_dicom(file_id)
    path = patient_dicom_path(item, relative_filename)
    dataset = pydicom.dcmread(str(path), force=True)
    if "PixelData" not in dataset:
        raise ValueError("该 DICOM 文件没有像素数据。")

    pixels = dataset.pixel_array
    if pixels.ndim == 4:
        pixels = pixels[0]
    if pixels.ndim == 3 and pixels.shape[-1] not in (3, 4):
        pixels = pixels[0]

    if pixels.ndim == 3 and pixels.shape[-1] in (3, 4):
        image_array = pixels.astype(np.float32) / 255
        image_array = np.clip((image_array - 0.5) * max(contrast, 0.01) + 0.5 + brightness, 0, 1) * 255
        image_array = image_array.astype(np.uint8)
        image = Image.fromarray(image_array[..., :3], "RGB")
    else:
        image_array = pixels.astype(np.float32)
        slope = float(getattr(dataset, "RescaleSlope", 1) or 1)
        intercept = float(getattr(dataset, "RescaleIntercept", 0) or 0)
        image_array = image_array * slope + intercept

        center = window_center if window_center is not None else getattr(dataset, "WindowCenter", None)
        width = window_width if window_width is not None else getattr(dataset, "WindowWidth", None)
        if hasattr(center, "__iter__") and not isinstance(center, (str, bytes)):
            center = center[0]
        if hasattr(width, "__iter__") and not isinstance(width, (str, bytes)):
            width = width[0]
        if center is not None and width not in (None, 0):
            center = float(center)
            width = float(width)
            low = center - width / 2
            high = center + width / 2
        else:
            low = float(np.nanmin(image_array))
            high = float(np.nanmax(image_array))
        if high <= low:
            high = low + 1
        normalized = np.clip((image_array - low) / (high - low), 0, 1)
        normalized = np.clip((normalized - 0.5) * max(contrast, 0.01) + 0.5 + brightness, 0, 1)
        image_array = normalized * 255
        if getattr(dataset, "PhotometricInterpretation", "") == "MONOCHROME1":
            image_array = 255 - image_array
        image = Image.fromarray(image_array.astype(np.uint8), "L")

    image.thumbnail((1400, 1400))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
