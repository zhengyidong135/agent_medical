from __future__ import annotations

import shutil
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import PATIENT_NII_DIR
from nii import add_generated_nii_label, get_nii_item, nii_image_path


SEGMENTATION_JOBS: dict[str, dict[str, Any]] = {}
SEGMENTATION_JOBS_LOCK = threading.Lock()


TOTALSEGMENTATOR_PARTS: list[dict[str, Any]] = [
    {"key": "liver", "name": "肝脏", "task": "total", "roi_subset": ["liver"]},
    {"key": "spleen", "name": "脾脏", "task": "total", "roi_subset": ["spleen"]},
    {"key": "kidney", "name": "肾脏", "task": "total", "roi_subset": ["kidney_left", "kidney_right"]},
    {
        "key": "lung",
        "name": "肺",
        "task": "total",
        "roi_subset": [
            "lung_upper_lobe_left",
            "lung_lower_lobe_left",
            "lung_upper_lobe_right",
            "lung_middle_lobe_right",
            "lung_lower_lobe_right",
        ],
    },
    {"key": "heart", "name": "心脏", "task": "total", "roi_subset": ["heart"]},
    {"key": "pancreas", "name": "胰腺", "task": "total", "roi_subset": ["pancreas"]},
    {"key": "stomach", "name": "胃", "task": "total", "roi_subset": ["stomach"]},
    {"key": "colon", "name": "结肠", "task": "total", "roi_subset": ["colon"]},
    {
        "key": "vessels",
        "name": "主要血管",
        "task": "total",
        "roi_subset": ["aorta", "inferior_vena_cava", "portal_vein_and_splenic_vein"],
    },
    {
        "key": "vertebrae",
        "name": "椎体",
        "task": "total",
        "roi_subset": [
            "vertebrae_L5",
            "vertebrae_L4",
            "vertebrae_L3",
            "vertebrae_L2",
            "vertebrae_L1",
            "vertebrae_T12",
            "vertebrae_T11",
            "vertebrae_T10",
        ],
    },
]


def _part_config(part_key: str) -> dict[str, Any]:
    part = next((entry for entry in TOTALSEGMENTATOR_PARTS if entry["key"] == part_key), None)
    if not part:
        raise ValueError("请选择有效的分割部位。")
    return part


def _totalsegmentator_command() -> str:
    command = shutil.which("TotalSegmentator")
    if command:
        return command
    command = shutil.which("TotalSegmentator.exe")
    if command:
        return command
    raise ValueError("未找到 TotalSegmentator。请先在后端 Python 环境安装：pip install TotalSegmentator")


def _combine_masks(mask_paths: list[Path], output_path: Path) -> None:
    try:
        import nibabel as nib
        import numpy as np
    except ImportError as exc:
        raise ValueError("缺少 nibabel 或 numpy，无法合并分割结果。") from exc

    if not mask_paths:
        raise ValueError("TotalSegmentator 没有生成可用的分割结果。")

    first_image = nib.load(str(mask_paths[0]))
    combined = np.zeros(first_image.shape[:3], dtype=np.uint16)
    for index, mask_path in enumerate(mask_paths, start=1):
        mask_image = nib.load(str(mask_path))
        mask_data = np.asanyarray(mask_image.dataobj)
        if mask_data.ndim > 3:
            mask_data = mask_data[..., 0]
        combined[mask_data > 0] = index

    nib.save(nib.Nifti1Image(combined, first_image.affine, first_image.header), str(output_path))


def _append_device(devices: list[dict[str, Any]], device: dict[str, Any]) -> None:
    name = str(device.get("name", "")).strip().lower()
    if not name:
        return
    if any(str(entry.get("name", "")).strip().lower() == name for entry in devices):
        return
    devices.append(device)


def _detect_nvidia_smi_devices(devices: list[dict[str, Any]]) -> None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return
    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            return
        for line in result.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            memory = f", {parts[2]} MB" if len(parts) >= 3 and parts[2] else ""
            _append_device(
                devices,
                {
                    "type": "gpu",
                    "id": f"gpu:{parts[0]}",
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_mb": int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None,
                    "label": f"GPU {parts[0]} - {parts[1]}{memory}",
                    "backend": "cuda",
                    "usable": True,
                },
            )
    except Exception:
        return


def _detect_windows_display_devices(devices: list[dict[str, Any]]) -> None:
    wmic = shutil.which("wmic")
    if not wmic:
        return
    try:
        result = subprocess.run(
            [wmic, "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            return
        display_index = 0
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("node,") or "," not in line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 3:
                continue
            ram_text = parts[-2]
            name = parts[-1]
            if not name:
                continue
            memory_mb = int(int(ram_text) / 1024 / 1024) if ram_text.isdigit() else None
            is_nvidia = "nvidia" in name.lower()
            label = f"GPU {display_index} - {name}"
            if memory_mb:
                label += f", {memory_mb} MB"
            if not is_nvidia:
                label += "（检测到，但 TotalSegmentator 通常需要 NVIDIA CUDA）"
            _append_device(
                devices,
                {
                    "type": "gpu",
                    "id": f"gpu:{display_index}" if is_nvidia else f"display:{display_index}",
                    "index": display_index,
                    "name": name,
                    "memory_mb": memory_mb,
                    "label": label,
                    "backend": "cuda" if is_nvidia else "display",
                    "usable": is_nvidia,
                },
            )
            display_index += 1
    except Exception:
        return


def detect_segmentation_devices() -> dict[str, Any]:
    devices: list[dict[str, Any]] = [{"type": "cpu", "id": "cpu", "name": "CPU", "label": "CPU", "usable": True}]
    _detect_nvidia_smi_devices(devices)
    _detect_windows_display_devices(devices)
    return {"devices": devices, "gpu_count": len([device for device in devices if device["type"] == "gpu"])}


def _job_snapshot(job_id: str) -> dict[str, Any]:
    with SEGMENTATION_JOBS_LOCK:
        job = SEGMENTATION_JOBS.get(job_id)
        if not job:
            raise ValueError("分割任务不存在。")
        return dict(job)


def _update_job(job_id: str, **updates: Any) -> None:
    with SEGMENTATION_JOBS_LOCK:
        if job_id in SEGMENTATION_JOBS:
            SEGMENTATION_JOBS[job_id].update(updates)
            SEGMENTATION_JOBS[job_id]["updated_at"] = time.time()


def get_segmentation_job(job_id: str) -> dict[str, Any]:
    return _job_snapshot(job_id)


def start_totalsegmentator_job(file_id: str, part_key: str, device_id: str = "cpu") -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "file_id": file_id,
        "part": part_key,
        "device": device_id,
        "status": "queued",
        "progress": 5,
        "message": "分割任务已创建",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with SEGMENTATION_JOBS_LOCK:
        SEGMENTATION_JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_totalsegmentator_job,
        args=(job_id, file_id, part_key, device_id),
        daemon=True,
    )
    thread.start()
    return _job_snapshot(job_id)


def _run_totalsegmentator_job(job_id: str, file_id: str, part_key: str, device_id: str) -> None:
    try:
        _update_job(job_id, status="running", progress=15, message="TotalSegmentator 正在运行")
        result = run_totalsegmentator(file_id, part_key, device_id=device_id)
        _update_job(job_id, status="done", progress=100, message="分割完成", result=result)
    except Exception as exc:
        _update_job(job_id, status="error", progress=100, message=str(exc), error=str(exc))


def run_totalsegmentator(
    file_id: str,
    part_key: str,
    timeout_seconds: int = 1800,
    device_id: str = "cpu",
) -> dict[str, Any]:
    part = _part_config(part_key)
    command = _totalsegmentator_command()
    item = get_nii_item(file_id)
    item_dir = PATIENT_NII_DIR / file_id
    image_path = nii_image_path(item_dir, item)
    if not image_path.exists():
        raise ValueError("上传的 NIfTI 图像文件不存在。")

    with tempfile.TemporaryDirectory(prefix="totalseg-") as temp_dir:
        output_dir = Path(temp_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            command,
            "-i",
            str(image_path),
            "-o",
            str(output_dir),
            "--task",
            part.get("task", "total"),
        ]
        roi_subset = part.get("roi_subset") or []
        if roi_subset:
            cmd.extend(["--roi_subset", *roi_subset])
        env = None
        if device_id.startswith("gpu:"):
            gpu_index = device_id.split(":", 1)[1]
            cmd.extend(["--device", "gpu"])
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu_index)
        else:
            cmd.extend(["--device", "cpu"])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise ValueError(f"TotalSegmentator 分割失败：{detail or result.returncode}")

        mask_paths = [output_dir / f"{roi}.nii.gz" for roi in roi_subset if (output_dir / f"{roi}.nii.gz").exists()]
        if not mask_paths:
            mask_paths = sorted(output_dir.glob("*.nii.gz"))
        label_filename = f"totalsegmentator_{part['key']}_{uuid.uuid4().hex[:6]}.nii.gz"
        combined_path = Path(temp_dir) / label_filename
        _combine_masks(mask_paths, combined_path)

        updated_item = add_generated_nii_label(file_id, combined_path, f"TotalSegmentator-{part['name']}", part["name"])
        label = (updated_item.get("labels") or [])[-1] if updated_item.get("labels") else None
        return {"item": updated_item, "label": label, "part": part}
