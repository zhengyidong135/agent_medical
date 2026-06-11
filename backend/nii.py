from __future__ import annotations

import io
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from config import (
    PATIENT_NII_DIR,
    load_nii_index,
    save_nii_index,
    ensure_nii_store,
    safe_filename,
)

def is_nii_gz(filename: str) -> bool:
    return filename.lower().endswith(".nii.gz")


def nii_pair_key(filename: str) -> str:
    name = Path(filename).name.lower()
    if name.endswith(".nii.gz"):
        name = name[:-7]
    name = re.sub(r"(^|[_\-.])(image|img|label|labels|seg|segmentation|mask|gt)([_\-.]|$)", "_", name)
    name = re.sub(r"[_\-.]+", "_", name).strip("_")
    return name


def nii_shape(path: Path) -> list[int]:
    try:
        import nibabel as nib
    except ImportError as exc:
        raise ValueError("缺少 nibabel，无法解析 nii.gz 文件。") from exc
    image = nib.load(str(path))
    return [int(value) for value in image.shape[:3]]


def validate_nii_image_volume(path: Path) -> None:
    try:
        import nibabel as nib
        import numpy as np
    except ImportError as exc:
        raise ValueError("缺少 nibabel 或 numpy，无法解析 nii.gz 文件。") from exc

    data = np.asanyarray(nib.load(str(path)).dataobj)
    if data.ndim > 3:
        data = data[..., 0]
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        raise ValueError("上传的图像没有有效体素值。")

    unique_values = np.unique(finite)
    if unique_values.size <= 32 and np.nanmin(finite) >= 0 and np.nanmax(finite) <= 32:
        raise ValueError("上传的图像看起来是标签掩膜，不是 CT/MRI 灰度图。请在“图像”处上传原始 CT/MRI，在“标签”处上传掩膜。")


def nii_label_class_info(path: Path) -> dict[str, Any]:
    try:
        import nibabel as nib
        import numpy as np
    except ImportError as exc:
        raise ValueError("缺少 nibabel 或 numpy，无法解析 nii.gz 标签文件。") from exc

    data = np.asanyarray(nib.load(str(path)).dataobj)
    if data.ndim > 3 and data.shape[3] > 1:
        active_channels = [idx for idx in range(data.shape[3]) if np.any(data[:, :, :, idx] > 0)]
        return {
            "class_count": max(1, len(active_channels)),
            "class_values": [int(idx + 1) for idx in active_channels],
            "label_kind": "multi" if len(active_channels) > 1 else "single",
        }

    if data.ndim > 3:
        data = data[..., 0]
    finite = data[np.isfinite(data)]
    positive_values = np.unique(finite[finite > 0])
    class_values = []
    for value in positive_values:
        try:
            class_values.append(int(round(float(value))))
        except (TypeError, ValueError, OverflowError):
            class_values.append(len(class_values) + 1)
    class_count = max(1, len(class_values))
    return {
        "class_count": class_count,
        "class_values": class_values,
        "label_kind": "multi" if class_count > 1 else "single",
    }


NII_LABEL_COLORS = [
    "#ff0000",
    "#ffd600",
    "#0066ff",
    "#00c853",
    "#9c27b0",
    "#00bcd4",
    "#ff6d00",
    "#ff1493",
]


def build_nii_label_meta(filename: str, index: int) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "name": f"标签{index}",
        "filename": filename,
        "part": "",
        "color": NII_LABEL_COLORS[(index - 1) % len(NII_LABEL_COLORS)],
        "class_count": 1,
        "class_values": [1],
        "label_kind": "single",
    }


def normalize_nii_labels(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Migrate old label format to new structure with id/name/part/color."""
    labels = item.get("labels")
    if not isinstance(labels, list):
        labels = []
        if item.get("label_filename"):
            labels = [{"filename": item["label_filename"]}]
    result = []
    for idx, entry in enumerate(labels):
        if "id" in entry and "color" in entry:
            entry.setdefault("class_count", 1)
            entry.setdefault("class_values", [1])
            entry.setdefault("label_kind", "single")
            result.append(entry)
        else:
            result.append(build_nii_label_meta(entry.get("filename", ""), idx + 1))
    return result


def refresh_nii_label_class_info(item: dict[str, Any]) -> dict[str, Any]:
    item_dir = PATIENT_NII_DIR / item.get("id", "")
    labels = normalize_nii_labels(item)
    changed = False
    for label in labels:
        filename = label.get("filename", "")
        if not filename:
            continue
        label_path = nii_label_path(item_dir, filename)
        if not label_path.exists():
            continue
        try:
            info = nii_label_class_info(label_path)
        except Exception:
            continue
        for key, value in info.items():
            if label.get(key) != value:
                label[key] = value
                changed = True
    item["labels"] = labels
    if changed:
        items = load_nii_index()
        for idx, existing in enumerate(items):
            if existing.get("id") == item.get("id"):
                items[idx] = item
                save_nii_index(items)
                break
    return item


def save_uploaded_nii_pairs(image_uploads: list[Any], label_uploads: list[Any] | None = None) -> list[dict[str, Any]]:
    ensure_nii_store()
    image_uploads = [upload for upload in image_uploads if is_nii_gz(upload.filename)]
    if not image_uploads:
        raise ValueError("请上传至少一个图像 nii.gz 文件。")
    if len(image_uploads) != 1:
        raise ValueError("图像一次只能上传一个 nii.gz 文件。")

    items = load_nii_index()
    saved = []
    for image_upload in image_uploads:
        key = nii_pair_key(image_upload.filename)
        file_id = uuid.uuid4().hex
        item_dir = PATIENT_NII_DIR / file_id
        item_dir.mkdir(parents=True, exist_ok=True)
        try:
            image_name = safe_filename(Path(image_upload.filename).name)
            image_path = item_dir / image_name
            with image_path.open("wb") as target:
                shutil.copyfileobj(image_upload.file, target)

            shape = nii_shape(image_path)
            item = {
                "id": file_id,
                "name": key,
                "image_filename": image_name,
                "labels": [],
                "shape": shape,
                "slice_count": shape[2] if len(shape) >= 3 else 1,
                "size": image_path.stat().st_size,
                "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            }
        except Exception:
            shutil.rmtree(item_dir, ignore_errors=True)
            raise
        items.append(item)
        saved.append(item)
    save_nii_index(items)
    return saved


def get_nii_item(file_id: str) -> dict[str, Any]:
    item = next((entry for entry in load_nii_index() if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("NIfTI 数据不存在。")
    return item


def nii_image_path(item_dir: Path, item: dict[str, Any]) -> Path:
    return item_dir / item["image_filename"]


def nii_label_path(item_dir: Path, filename: str) -> Path:
    separated_path = item_dir / "labels" / filename
    if separated_path.exists():
        return separated_path
    return item_dir / filename


def delete_nii_item(file_id: str) -> dict[str, Any]:
    items = load_nii_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("NIfTI 数据不存在。")
    shutil.rmtree(PATIENT_NII_DIR / file_id, ignore_errors=True)
    save_nii_index([entry for entry in items if entry.get("id") != file_id])
    return item


def add_nii_labels(file_id: str, label_uploads: list[Any]) -> dict[str, Any]:
    label_uploads = [upload for upload in label_uploads if getattr(upload, "filename", "") and is_nii_gz(upload.filename)]
    if not label_uploads:
        raise ValueError("请上传至少一个标签 nii.gz 文件。")

    items = load_nii_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("NIfTI 数据不存在。")

    item_dir = PATIENT_NII_DIR / file_id
    labels_dir = item_dir / "labels"
    item_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    image_shape = item.get("shape") or nii_shape(nii_image_path(item_dir, item))
    labels_meta = normalize_nii_labels(item)

    for label_upload in label_uploads:
        label_name = safe_filename(Path(label_upload.filename).name)
        # Avoid overwriting existing files: add unique suffix if collision
        if (labels_dir / label_name).exists():
            stem = label_name[:-7] if label_name.lower().endswith(".nii.gz") else label_name
            label_name = f"{stem}_{uuid.uuid4().hex[:6]}.nii.gz"
        target_path = labels_dir / label_name
        with target_path.open("wb") as target:
            shutil.copyfileobj(label_upload.file, target)
        label_shape = nii_shape(target_path)
        if label_shape != image_shape:
            target_path.unlink(missing_ok=True)
            raise ValueError(f"标签尺寸不匹配: {label_name}")
        label_meta = build_nii_label_meta(label_name, len(labels_meta) + 1)
        label_meta.update(nii_label_class_info(target_path))
        labels_meta.append(label_meta)

    item["labels"] = labels_meta
    item["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_nii_index(items)
    return item


def add_generated_nii_label(file_id: str, label_path: Path, label_name: str, part: str = "") -> dict[str, Any]:
    items = load_nii_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("NIfTI 数据不存在。")

    item_dir = PATIENT_NII_DIR / file_id
    labels_dir = item_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    image_shape = item.get("shape") or nii_shape(nii_image_path(item_dir, item))
    label_shape = nii_shape(label_path)
    if label_shape != image_shape:
        raise ValueError(f"分割结果尺寸不匹配: {label_path.name}")

    target_name = safe_filename(label_path.name)
    if (labels_dir / target_name).exists():
        stem = target_name[:-7] if target_name.lower().endswith(".nii.gz") else target_name
        target_name = f"{stem}_{uuid.uuid4().hex[:6]}.nii.gz"
    target_path = labels_dir / target_name
    shutil.copyfile(label_path, target_path)

    labels_meta = normalize_nii_labels(item)
    label_meta = build_nii_label_meta(target_name, len(labels_meta) + 1)
    label_meta["name"] = label_name
    label_meta["part"] = part
    label_meta.update(nii_label_class_info(target_path))
    labels_meta.append(label_meta)

    item["labels"] = labels_meta
    item["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_nii_index(items)
    return item


def update_nii_label(file_id: str, label_id: str, data: dict[str, Any]) -> dict[str, Any]:
    items = load_nii_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("NIfTI 数据不存在。")
    labels = normalize_nii_labels(item)
    label = next((entry for entry in labels if entry.get("id") == label_id), None)
    if not label:
        raise ValueError("标签不存在。")
    if "name" in data:
        label["name"] = data["name"]
    if "part" in data:
        label["part"] = data["part"]
    if "color" in data:
        label["color"] = data["color"]
    item["labels"] = labels
    item["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_nii_index(items)
    return item


def delete_nii_label(file_id: str, label_id: str) -> dict[str, Any]:
    items = load_nii_index()
    item = next((entry for entry in items if entry.get("id") == file_id), None)
    if not item:
        raise ValueError("NIfTI 数据不存在。")
    labels = normalize_nii_labels(item)
    label = next((entry for entry in labels if entry.get("id") == label_id), None)
    if not label:
        raise ValueError("标签不存在。")
    # Delete file from disk
    item_dir = PATIENT_NII_DIR / file_id
    label_path = nii_label_path(item_dir, label["filename"])
    label_path.unlink(missing_ok=True)
    item["labels"] = [entry for entry in labels if entry.get("id") != label_id]
    item["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_nii_index(items)
    return item


def hex_to_rgba(color: str, alpha: int = 110) -> list[int]:
    """Convert '#rrggbb' to [r, g, b, alpha]."""
    color = color.lstrip("#")
    if len(color) != 6:
        return [255, 64, 64, alpha]
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return [r, g, b, alpha]


def label_value_rgba(base_color: str, label_index: int, value_index: int, alpha: int = 110) -> list[int]:
    if value_index == 0:
        return hex_to_rgba(base_color, alpha)
    palette_index = (label_index + value_index) % len(NII_LABEL_COLORS)
    return hex_to_rgba(NII_LABEL_COLORS[palette_index], alpha)


def label_index_rgba(index: int, alpha: int = 110) -> list[int]:
    return hex_to_rgba(NII_LABEL_COLORS[index % len(NII_LABEL_COLORS)], alpha)


def mask_boundary(mask: Any) -> Any:
    boundary = mask.copy()
    boundary[1:-1, 1:-1] = mask[1:-1, 1:-1] & (
        ~mask[:-2, 1:-1]
        | ~mask[2:, 1:-1]
        | ~mask[1:-1, :-2]
        | ~mask[1:-1, 2:]
    )
    return boundary


def render_nii_png(file_id: str, slice_index: int = 0, label_ids: set[str] | None = None) -> bytes:
    try:
        import nibabel as nib
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise ValueError("缺少 nibabel、numpy 或 Pillow，无法显示 nii.gz 图像。") from exc

    item = get_nii_item(file_id)
    item_dir = PATIENT_NII_DIR / file_id
    image_data = np.asanyarray(nib.load(str(nii_image_path(item_dir, item))).dataobj)
    if image_data.ndim > 3:
        image_data = image_data[..., 0]
    slice_index = max(0, min(int(slice_index), image_data.shape[2] - 1))
    image_slice = image_data[:, :, slice_index].astype(np.float32)

    finite_slice = image_slice[np.isfinite(image_slice)]
    nonzero_slice = finite_slice[finite_slice != 0]
    intensity_source = nonzero_slice if nonzero_slice.size > 16 else finite_slice
    if intensity_source.size <= 1:
        volume = image_data.astype(np.float32)
        finite_volume = volume[np.isfinite(volume)]
        nonzero_volume = finite_volume[finite_volume != 0]
        intensity_source = nonzero_volume if nonzero_volume.size > 16 else finite_volume
    if intensity_source.size <= 1:
        intensity_source = np.array([0, 1], dtype=np.float32)

    low = float(np.nanpercentile(intensity_source, 1))
    high = float(np.nanpercentile(intensity_source, 99))
    if high <= low:
        low = float(np.nanmin(intensity_source))
        high = float(np.nanmax(intensity_source))
        if high <= low:
            high = low + 1
    normalized = np.clip((image_slice - low) / (high - low), 0, 1) * 255
    base = Image.fromarray(normalized.astype(np.uint8).T, "L").convert("RGBA")
    base_pixels = np.array(base, dtype=np.uint8)

    labels = normalize_nii_labels(item)
    visible_labels = [
        (label_index, label_entry)
        for label_index, label_entry in enumerate(labels)
        if label_ids is None or label_entry.get("id", "") in label_ids
    ]

    for _label_index, label_entry in visible_labels:
        label_filename = label_entry.get("filename", "")
        if not label_filename:
            continue
        label_path = nii_label_path(item_dir, label_filename)
        if not label_path.exists():
            continue
        label_data = np.asanyarray(nib.load(str(label_path)).dataobj)
        if label_data.ndim < 3 or slice_index >= label_data.shape[2]:
            continue

        if label_data.ndim > 3 and label_data.shape[3] > 1:
            active_channels = [
                channel_index
                for channel_index in range(label_data.shape[3])
                if np.any(label_data[:, :, :, channel_index] > 0)
            ]
            is_multi_label = len(active_channels) > 1
            for channel_index in active_channels:
                label_slice = label_data[:, :, slice_index, channel_index].T
                mask = label_slice > 0
                if not np.any(mask):
                    continue
                color_index = channel_index if is_multi_label else 0
                boundary = mask_boundary(mask)
                color = np.array(label_index_rgba(color_index, 255)[:3], dtype=np.float32)
                alpha = 0.55 if is_multi_label else 0.35
                base_pixels[mask, :3] = (base_pixels[mask, :3].astype(np.float32) * (1 - alpha) + color * alpha).astype(np.uint8)
                base_pixels[boundary, :3] = color.astype(np.uint8)
                base_pixels[mask, 3] = 255
        else:
            if label_data.ndim > 3:
                label_data = label_data[..., 0]
            positive_values = [value for value in np.unique(label_data) if value > 0]
            value_color_map = {value: value_index for value_index, value in enumerate(positive_values)}
            is_multi_label = len(positive_values) > 1
            label_slice = label_data[:, :, slice_index].T
            values = [value for value in np.unique(label_slice) if value > 0]
            for value_index, value in enumerate(values):
                mask = label_slice == value
                if not np.any(mask):
                    continue
                if is_multi_label:
                    color_index = value_color_map.get(value, value_index)
                else:
                    color_index = 0
                boundary = mask_boundary(mask)
                color = np.array(label_index_rgba(color_index, 255)[:3], dtype=np.float32)
                alpha = 0.55 if is_multi_label else 0.35
                base_pixels[mask, :3] = (base_pixels[mask, :3].astype(np.float32) * (1 - alpha) + color * alpha).astype(np.uint8)
                base_pixels[boundary, :3] = color.astype(np.uint8)
                base_pixels[mask, 3] = 255

    output = io.BytesIO()
    base = Image.fromarray(base_pixels, "RGBA")
    base.save(output, format="PNG")
    return output.getvalue()
