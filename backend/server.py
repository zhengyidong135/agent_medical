from __future__ import annotations

import cgi
import json
import os
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import FRONTEND_DIR, ENV_PATH, MODELS, load_env
from rag import (
    load_rag_index,
    rebuild_all_rag_texts,
    save_uploaded_rag_file,
    delete_rag_file,
    get_rag_file,
    get_rag_text,
    build_rag_docx,
)
from dicom import (
    load_patient_index,
    save_uploaded_dicom_folder,
    delete_patient_dicom,
    update_patient_dicom,
    list_patient_dicom_images,
    render_dicom_png,
    optional_float,
)
from nii import (
    load_nii_index,
    refresh_nii_label_class_info,
    save_uploaded_nii_pairs,
    add_nii_labels,
    update_nii_label,
    delete_nii_label,
    delete_nii_item,
    render_nii_png,
)
from model import call_model
from segmentation import (
    TOTALSEGMENTATOR_PARTS,
    detect_segmentation_devices,
    get_segmentation_job,
    run_totalsegmentator,
    start_totalsegmentator_job,
)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/models":
            self.send_json({"models": MODELS, "tools": ["get_current_time", "get_weather"]})
            return
        if self.path == "/api/rag/files":
            self.send_json({"files": load_rag_index()})
            return
        if self.path == "/api/patients/dicom":
            self.send_json({"patients": load_patient_index()})
            return
        if self.path == "/api/patients/nii":
            items = load_nii_index()
            for idx, item in enumerate(items):
                items[idx] = refresh_nii_label_class_info(item)
            self.send_json({"items": items})
            return
        if self.path == "/api/segmentation/totalsegmentator/parts":
            self.send_json({"parts": TOTALSEGMENTATOR_PARTS})
            return
        if self.path == "/api/segmentation/devices":
            self.send_json(detect_segmentation_devices())
            return
        if self.path.startswith("/api/segmentation/jobs/"):
            try:
                job_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
                self.send_json({"job": get_segmentation_job(job_id)})
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, status=500)
            return
        if self.path.startswith("/api/patients/nii/"):
            self.handle_nii_viewer()
            return
        if self.path.startswith("/api/patients/dicom/"):
            self.handle_patient_dicom_viewer()
            return
        if self.path.startswith("/api/rag/files/"):
            self.handle_rag_download()
            return
        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/rag/upload":
            self.handle_rag_upload()
            return
        if self.path == "/api/rag/rebuild":
            try:
                self.send_json({"files": rebuild_all_rag_texts()})
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, status=500)
            return
        if self.path == "/api/patients/dicom/upload":
            self.handle_patient_dicom_upload()
            return
        if self.path == "/api/patients/nii/upload":
            self.handle_nii_upload()
            return
        if self.path.startswith("/api/patients/nii/") and self.path.endswith("/labels"):
            self.handle_nii_label_upload()
            return
        if self.path.startswith("/api/patients/nii/") and self.path.endswith("/segment"):
            self.handle_nii_segmentation()
            return
        if self.path.startswith("/api/patients/nii/") and self.path.endswith("/segment/jobs"):
            self.handle_nii_segmentation_job()
            return
        if self.path.startswith("/api/patients/nii/") and "/labels/" in self.path and self.path.endswith("/update"):
            self.handle_nii_label_update()
            return
        if self.path.startswith("/api/patients/dicom/") and self.path.endswith("/update"):
            self.handle_patient_dicom_update()
            return
        if self.path != "/api/chat":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            response = call_model(
                data.get("model", MODELS[0]),
                data.get("messages", []),
                bool(data.get("enableTools", True)),
                data.get("ragFileIds", []),
            )
            self.send_json(response)
        except Exception as exc:  # noqa: BLE001 - HTTP API should return useful errors.
            self.send_json({"error": str(exc)}, status=500)

    def do_DELETE(self) -> None:
        if self.path.startswith("/api/rag/files/"):
            try:
                file_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
                item = delete_rag_file(file_id)
                self.send_json({"deleted": item})
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, status=500)
            return
        if self.path.startswith("/api/patients/dicom/"):
            try:
                file_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
                item = delete_patient_dicom(file_id)
                self.send_json({"deleted": item})
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, status=500)
            return
        if self.path.startswith("/api/patients/nii/") and "/labels/" in self.path:
            try:
                parsed = urllib.parse.urlparse(self.path)
                parts = parsed.path.split("/")
                file_id = urllib.parse.unquote(parts[4])
                label_id = urllib.parse.unquote(parts[6])
                item = delete_nii_label(file_id, label_id)
                self.send_json({"item": item})
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, status=500)
            return
        if self.path.startswith("/api/patients/nii/"):
            try:
                file_id = urllib.parse.unquote(self.path.rsplit("/", 1)[-1])
                item = delete_nii_item(file_id)
                self.send_json({"deleted": item})
            except Exception as exc:  # noqa: BLE001
                self.send_json({"error": str(exc)}, status=500)
            return
        self.send_error(404, "Not found")

    def handle_rag_upload(self) -> None:
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            uploads = form["files"] if "files" in form else []
            if not isinstance(uploads, list):
                uploads = [uploads]
            saved = []
            errors = []
            for upload in uploads:
                if not getattr(upload, "filename", ""):
                    continue
                try:
                    saved.append(save_uploaded_rag_file(upload.filename, upload.file))
                except Exception as exc:  # noqa: BLE001 - return per-file upload errors.
                    errors.append({"filename": upload.filename, "error": str(exc)})
            self.send_json({"files": saved, "errors": errors})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_patient_dicom_upload(self) -> None:
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            uploads = form["files"] if "files" in form else []
            if not isinstance(uploads, list):
                uploads = [uploads]
            uploads = [upload for upload in uploads if getattr(upload, "filename", "")]
            if not uploads:
                self.send_json({"error": "请选择一个 DICOM 文件夹。"}, status=400)
                return
            item = save_uploaded_dicom_folder(uploads)
            self.send_json({"patients": [item], "errors": item.get("errors", [])})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_nii_upload(self) -> None:
        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            image_uploads = form["images"] if "images" in form else []
            if not isinstance(image_uploads, list):
                image_uploads = [image_uploads]
            image_uploads = [upload for upload in image_uploads if getattr(upload, "filename", "")]
            saved = save_uploaded_nii_pairs(image_uploads)
            self.send_json({"items": saved})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_nii_label_upload(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            if len(parts) < 6:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            uploads = form["labels"] if "labels" in form else []
            if not isinstance(uploads, list):
                uploads = [uploads]
            item = add_nii_labels(file_id, uploads)
            self.send_json({"item": item})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_nii_label_update(self) -> None:
        try:
            # POST /api/patients/nii/<file_id>/labels/<label_id>/update
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            file_id = urllib.parse.unquote(parts[4])
            label_id = urllib.parse.unquote(parts[6])
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            item = update_nii_label(file_id, label_id, data)
            self.send_json({"item": item})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_nii_segmentation(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            if len(parts) < 6:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            result = run_totalsegmentator(file_id, data.get("part", "liver"), device_id=data.get("device", "cpu"))
            self.send_json(result)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_nii_segmentation_job(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            if len(parts) < 7:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            job = start_totalsegmentator_job(file_id, data.get("part", "liver"), data.get("device", "cpu"))
            self.send_json({"job": job})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_nii_viewer(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            if len(parts) < 6:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            action = parts[5]
            if action == "image":
                query = urllib.parse.parse_qs(parsed.query)
                slice_index = int(query.get("slice", ["0"])[0] or 0)
                # Parse label_ids: ?labels=id1,id2 or ?label=0 for none
                labels_param = query.get("labels", [""])[0]
                if labels_param:
                    label_ids: set[str] | None = set(labels_param.split(","))
                elif query.get("label", ["1"])[0] == "0":
                    label_ids = set()
                else:
                    label_ids = None  # show all
                payload = render_nii_png(file_id, slice_index, label_ids)
                self.send_bytes(payload, "image/png", f"{file_id}-{slice_index}.png", inline=True)
                return
            self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_patient_dicom_update(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            if len(parts) < 6:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            item = update_patient_dicom(file_id, data)
            self.send_json({"patient": item})
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_patient_dicom_viewer(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            parts = parsed.path.split("/")
            if len(parts) < 6:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            action = parts[5]
            if action == "images":
                self.send_json(list_patient_dicom_images(file_id))
                return
            if action == "image":
                query = urllib.parse.parse_qs(parsed.query)
                relative_filename = query.get("file", [""])[0]
                payload = render_dicom_png(
                    file_id,
                    relative_filename,
                    window_width=optional_float(query.get("window_width", [""])[0]),
                    window_center=optional_float(query.get("window_center", [""])[0]),
                    contrast=optional_float(query.get("contrast", ["1"])[0]) or 1,
                    brightness=optional_float(query.get("brightness", ["0"])[0]) or 0,
                )
                self.send_bytes(payload, "image/png", f"{Path(relative_filename).stem or file_id}.png", inline=True)
                return
            self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def handle_rag_download(self) -> None:
        try:
            parts = self.path.split("/")
            if len(parts) < 6:
                self.send_error(404, "Not found")
                return
            file_id = urllib.parse.unquote(parts[4])
            export_type = parts[5].split("?", 1)[0]
            item = get_rag_file(file_id)
            stem = Path(item.get("filename", file_id)).stem or file_id
            if export_type == "text":
                text = get_rag_text(file_id).encode("utf-8")
                self.send_bytes(text, "text/plain; charset=utf-8", f"{stem}.txt")
                return
            if export_type == "docx":
                payload = build_rag_docx(file_id)
                self.send_bytes(
                    payload,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    f"{stem}.docx",
                )
                return
            self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=500)

    def send_bytes(self, payload: bytes, content_type: str, filename: str, inline: bool = False) -> None:
        quoted = urllib.parse.quote(filename)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        disposition = "inline" if inline else "attachment"
        self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quoted}")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

def main() -> None:
    load_env(ENV_PATH)
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"模型智能体网站已启动: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
