#!/usr/bin/env python3
import os
import sys
import json
import time
import shutil
import platform
import subprocess
import threading
import webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from analyze import analyze_photos, find_image_files
from mosaic import generate_mosaic_pipeline
from dzi import generate_dzi_pyramid
from generate import resolve_target_path, setup_web_viewer, load_config, SUPPORTED_EXTENSIONS

# Global state for background generation
GEN_STATE = {
    "busy": False,
    "step": "Готов к работе",
    "percent": 0,
    "error": None,
    "timestamp": int(time.time()),
    "last_result": None
}
STATE_LOCK = threading.Lock()


def update_state(step=None, percent=None, error=None, busy=None, last_result=None):
    with STATE_LOCK:
        if step is not None:
            GEN_STATE["step"] = step
        if percent is not None:
            GEN_STATE["percent"] = percent
        if error is not None:
            GEN_STATE["error"] = error
        if busy is not None:
            GEN_STATE["busy"] = busy
        if last_result is not None:
            GEN_STATE["last_result"] = last_result
            GEN_STATE["timestamp"] = int(time.time())


def run_generation_task(options: dict):
    try:
        update_state(busy=True, step="Поиск исходных файлов...", percent=5, error=None)

        config_path = SCRIPT_DIR / "config.json"
        base_config = load_config(config_path)

        # Merge options
        grid_cfg = base_config.setdefault("grid", {})
        matching_cfg = base_config.setdefault("matching", {})
        output_cfg = base_config.setdefault("output", {})

        if "columns" in options:
            grid_cfg["columns"] = int(options["columns"])
        if "tile_render_size" in options:
            grid_cfg["tile_render_size"] = int(options["tile_render_size"])
        if "color_blend_ratio" in options:
            matching_cfg["color_blend_ratio"] = float(options["color_blend_ratio"])
        if "skip_transparent" in options:
            matching_cfg["skip_transparent"] = bool(options["skip_transparent"])
        if "unique_only" in options:
            matching_cfg["unique_only"] = bool(options["unique_only"])
        if "random_top_k" in options:
            matching_cfg["random_top_k"] = int(options["random_top_k"])
        if "avoid_neighbor_radius" in options:
            matching_cfg["avoid_neighbor_radius"] = int(options["avoid_neighbor_radius"])
        if "max_repeat_factor" in options:
            matching_cfg["max_repeat_factor"] = float(options["max_repeat_factor"])

        # Target and photos paths
        target_path = resolve_target_path(options.get("target_path") or base_config.get("target_path"), PROJECT_ROOT)
        photos_dir = Path(options.get("photos_dir") or base_config.get("photos_dir", PROJECT_ROOT / "source" / "photos"))
        if not photos_dir.is_absolute():
            photos_dir = (PROJECT_ROOT / photos_dir).resolve()

        output_dir = PROJECT_ROOT / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        setup_web_viewer(output_dir)

        cache_dir = PROJECT_ROOT / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        if not target_path or not target_path.exists():
            raise FileNotFoundError("Целевой портрет не найден в папке source/ или target/!")

        if not photos_dir.exists():
            raise FileNotFoundError(f"Папка с фотографиями не найдена: {photos_dir}")

        update_state(step="Анализ коллекции фотографий...", percent=15)
        thumbs_output_dir = output_dir / "assets" / "thumbs"
        photos_meta = analyze_photos(
            photos_dir=photos_dir,
            cache_dir=cache_dir,
            output_thumbs_dir=thumbs_output_dir,
            thumb_size=240,
            cell_aspect_ratio=float(grid_cfg.get("cell_aspect_ratio", 1.0)),
            force_refresh=options.get("force_analyze", False)
        )

        if not photos_meta:
            raise ValueError("Не найдено корректных фотографий в папке photos/")

        update_state(step="Подбор ячеек и расчет мозаики...", percent=45)
        mosaic_img, metadata = generate_mosaic_pipeline(
            target_path=target_path,
            photos_meta=photos_meta,
            output_dir=output_dir,
            config=base_config
        )

        update_state(step="Генерация многоуровневых тайлов (Deep Zoom)...", percent=75)
        dzi_tile_size = int(output_cfg.get("dzi_tile_size", 256))
        dzi_overlap = int(output_cfg.get("dzi_overlap", 1))
        out_format = output_cfg.get("format", "jpg")
        quality = int(output_cfg.get("quality", 90))

        generate_dzi_pyramid(
            source_image=mosaic_img,
            output_dir=output_dir,
            basename="mosaic",
            tile_size=dzi_tile_size,
            overlap=dzi_overlap,
            image_format=out_format,
            quality=quality
        )

        update_state(
            busy=False,
            step="Генерация успешно завершена!",
            percent=100,
            error=None,
            last_result={
                "columns": metadata["grid"]["columns"],
                "rows": metadata["grid"]["rows"],
                "total_cells": metadata["grid"]["total_cells"],
                "filled_cells": metadata["stats"].get("filled_cells", metadata["grid"]["total_cells"]),
                "unique_photos_used": metadata["stats"]["unique_photos_used"],
                "width": metadata["image"]["width"],
                "height": metadata["image"]["height"],
                "file": metadata["image"]["file"]
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        update_state(busy=False, step="Ошибка сборки", percent=0, error=str(e))


class StudioRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep console output concise
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("", "/"):
            self.serve_file(SCRIPT_DIR / "studio" / "index.html", "text/html; charset=utf-8")
            return

        if path.startswith("/studio/"):
            rel_path = path[len("/studio/"):]
            file_path = SCRIPT_DIR / "studio" / rel_path
            self.serve_static_file(file_path)
            return

        if path.startswith("/output/"):
            rel_path = path[len("/output/"):]
            file_path = PROJECT_ROOT / "output" / rel_path
            self.serve_static_file(file_path)
            return

        if path.startswith("/source/"):
            rel_path = path[len("/source/"):]
            file_path = PROJECT_ROOT / "source" / rel_path
            self.serve_static_file(file_path)
            return

        if path == "/api/status":
            self.handle_api_status()
            return

        if path == "/api/progress":
            self.handle_api_progress()
            return

        if path == "/api/open-folder":
            self.handle_open_folder()
            return

        # Fallback to standard handler
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                options = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                options = {}

            with STATE_LOCK:
                if GEN_STATE["busy"]:
                    self.send_json({"ok": False, "error": "Генерация уже выполняется"}, status=409)
                    return

            thread = threading.Thread(target=run_generation_task, args=(options,), daemon=True)
            thread.start()
            self.send_json({"ok": True, "message": "Сборка запущена"})
            return

        if path == "/api/upload-target":
            self.handle_upload_target()
            return

        self.send_error(404, "Not Found")

    def handle_api_status(self):
        config_path = SCRIPT_DIR / "config.json"
        config = load_config(config_path)

        target_path = resolve_target_path(config.get("target_path"), PROJECT_ROOT)
        photos_dir = PROJECT_ROOT / "source" / "photos"

        target_info = None
        if target_path and target_path.exists():
            target_info = {
                "filename": target_path.name,
                "size_mb": round(target_path.stat().st_size / (1024 * 1024), 2),
                "extension": target_path.suffix.lower()
            }

        photos_count = 0
        if photos_dir.exists():
            photos_count = len(find_image_files(photos_dir))

        mosaic_exists = (PROJECT_ROOT / "output" / "mosaic.dzi").exists()

        data = {
            "target": target_info,
            "photos_count": photos_count,
            "config": config,
            "mosaic_ready": mosaic_exists,
            "state": GEN_STATE
        }
        self.send_json(data)

    def handle_api_progress(self):
        with STATE_LOCK:
            data = dict(GEN_STATE)
        self.send_json(data)

    def handle_open_folder(self):
        output_dir = PROJECT_ROOT / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            current_os = platform.system()
            if current_os == "Windows":
                os.startfile(str(output_dir))
            elif current_os == "Darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, status=500)

    def handle_upload_target(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")

            # If raw binary or multipart
            target_dir = PROJECT_ROOT / "source"
            target_dir.mkdir(parents=True, exist_ok=True)

            # Look for boundary
            if "boundary=" in content_type:
                boundary = content_type.split("boundary=")[1].strip().encode()
                body = self.rfile.read(content_length)
                parts = body.split(b"--" + boundary)
                for part in parts:
                    if b'filename="' in part:
                        headers_part, file_data = part.split(b"\r\n\r\n", 1)
                        file_data = file_data.rstrip(b"\r\n")
                        # Parse filename
                        headers_str = headers_part.decode("latin1")
                        import re
                        m = re.search(r'filename="([^"]+)"', headers_str)
                        filename = m.group(1) if m else "target.png"
                        ext = os.path.splitext(filename)[1].lower()
                        if ext not in SUPPORTED_EXTENSIONS:
                            ext = ".png"

                        # Remove older targets
                        for old_ext in SUPPORTED_EXTENSIONS:
                            old_file = target_dir / f"target{old_ext}"
                            if old_file.exists():
                                old_file.unlink()

                        save_path = target_dir / f"target{ext}"
                        with open(save_path, "wb") as f:
                            f.write(file_data)

                        self.send_json({"ok": True, "filename": save_path.name})
                        return

            # Direct body stream fallback
            body = self.rfile.read(content_length)
            save_path = target_dir / "target.png"
            with open(save_path, "wb") as f:
                f.write(body)
            self.send_json({"ok": True, "filename": save_path.name})

        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, status=500)

    def serve_file(self, file_path: Path, content_type: str):
        if not file_path.exists():
            self.send_error(404, f"File not found: {file_path.name}")
            return
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))

    def serve_static_file(self, file_path: Path):
        if not file_path.exists() or file_path.is_dir():
            self.send_error(404, "Not Found")
            return

        ext = file_path.suffix.lower()
        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".xml": "application/xml; charset=utf-8",
            ".dzi": "application/xml; charset=utf-8",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon"
        }
        content_type = mime_types.get(ext, "application/octet-stream")
        self.serve_file(file_path, content_type)

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def start_studio_server(port: int = 8080, open_browser: bool = True):
    server_address = ("", port)
    ThreadingHTTPServer.allow_reuse_address = True
    
    # Try preferred port or increment if in use
    actual_port = port
    httpd = None
    for attempt_port in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer(("", attempt_port), StudioRequestHandler)
            actual_port = attempt_port
            break
        except OSError:
            continue

    if not httpd:
        print(f"[Error] Could not bind to any port between {port} and {port + 20}")
        sys.exit(1)

    url = f"http://localhost:{actual_port}/"
    print("=" * 60)
    print("PHOTOMOSAIC STUDIO (GUI)")
    print(f"Адрес студии: {url}")
    print("Для завершения нажмите Ctrl+C в этом окне.")
    print("=" * 60)

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Studio] Остановлено.")


if __name__ == "__main__":
    start_studio_server()
