import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from core.image_pipeline_core import process_paths

STAGING_DIR = Path.home() / "BCX" / "staging" / "clz_images"
VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class ImagePipelineTab:
    def __init__(self, parent, log, root_window):
        self._parent = parent
        self._log = log
        self._root = root_window

        self._frame = ttk.Frame(parent)
        self._build_ui()
        self._refresh_staging_stats()

    def frame(self):
        return self._frame

    # ======================================================
    # UI
    # ======================================================

    def _build_ui(self):
        pad = {"padx": 10, "pady": 8}

        ttk.Label(
            self._frame,
            text="Image Pipeline (Staging Only)",
            font=("Helvetica", 16, "bold"),
        ).pack(anchor="w", **pad)

        ttk.Label(
            self._frame,
            text=(
                "This pipeline automatically processes images from:\n\n"
                f"{STAGING_DIR}\n\n"
                "All images in staging (including subfolders) will be processed."
            ),
            justify="left",
        ).pack(anchor="w", **pad)

        btn_row = ttk.Frame(self._frame)
        btn_row.pack(anchor="w", padx=10, pady=(8, 0))

        ttk.Button(
            btn_row,
            text="Process Staging Images",
            command=self._run_pipeline,
        ).pack(side="left")

        ttk.Button(
            btn_row,
            text="Refresh staging stats",
            command=self._refresh_staging_stats,
        ).pack(side="left", padx=8)

        ttk.Button(
            btn_row,
            text="Clear Staged",
            command=self._clear_staged,
        ).pack(side="left", padx=8)

        self._stats_label = ttk.Label(self._frame, text="(loading...)")
        self._stats_label.pack(anchor="w", padx=10, pady=(8, 0))

        self._status = ttk.Label(self._frame, text="Idle")
        self._status.pack(anchor="w", padx=10, pady=(10, 0))

        self._progress = ttk.Progressbar(self._frame, orient="horizontal", mode="determinate", length=520)
        self._progress.pack(anchor="w", padx=10, pady=(4, 0))

    # ======================================================
    # STAGING HELPERS
    # ======================================================

    def _gather_images(self) -> list[str]:
        if not STAGING_DIR.exists():
            return []
        return [str(p) for p in STAGING_DIR.rglob("*") if p.is_file() and p.suffix.lower() in VALID_EXTS]

    def _refresh_staging_stats(self):
        # Make sure we never reference uninitialized locals
        img_count = 0
        series_count = 0
        try:
            paths = self._gather_images()
            img_count = len(paths)

            # series_count = number of immediate subfolders that contain at least one image
            if STAGING_DIR.exists():
                series_folders = set()
                for p in paths:
                    pp = Path(p)
                    rel = pp.relative_to(STAGING_DIR)
                    if len(rel.parts) >= 2:
                        series_folders.add(rel.parts[0])
                series_count = len(series_folders)

            if series_count > 0:
                self._stats_label.config(text=f"Staged images: {img_count}   •   Series folders: {series_count}")
            else:
                self._stats_label.config(text=f"Staged images: {img_count}")
        except Exception as e:
            self._stats_label.config(text=f"Error reading staging folder: {e}")

    def _clear_staged(self):
        if not STAGING_DIR.exists():
            messagebox.showinfo("Nothing to clear", f"Staging folder not found:\n{STAGING_DIR}")
            return

        paths = self._gather_images()
        if not paths:
            messagebox.showinfo("Nothing to clear", "No staged images found.")
            return

        ok = messagebox.askyesno(
            "Clear Staged Images",
            f"This will permanently delete {len(paths)} staged image file(s)\n"
            f"inside:\n{STAGING_DIR}\n\nContinue?",
        )
        if not ok:
            return

        deleted = 0
        errors = 0

        for raw in paths:
            try:
                Path(raw).unlink()
                deleted += 1
            except Exception:
                errors += 1

        # Remove empty subfolders (keep root)
        try:
            for d in sorted([p for p in STAGING_DIR.rglob("*") if p.is_dir()], reverse=True):
                try:
                    if d != STAGING_DIR and not any(d.iterdir()):
                        d.rmdir()
                except Exception:
                    pass
        except Exception:
            pass

        self._log(f"Clear Staged: deleted={deleted} errors={errors}")
        self._refresh_staging_stats()
        messagebox.showinfo("Clear Staged", f"Deleted: {deleted}\nErrors: {errors}")

    # ======================================================
    # PIPELINE
    # ======================================================

    def _run_pipeline(self):
        if not STAGING_DIR.exists():
            messagebox.showerror(
                "Staging Folder Missing",
                f"Staging folder not found:\n{STAGING_DIR}",
            )
            return

        image_paths = self._gather_images()
        if not image_paths:
            messagebox.showinfo("No Images", "No images found in the staging folder.")
            return

        total = len(image_paths)
        self._progress["value"] = 0
        self._status.config(text=f"0/{total} Starting…")
        self._log(f"Starting image pipeline on {total} images.")

        threading.Thread(
            target=self._process_images_thread,
            args=(image_paths,),
            daemon=True,
        ).start()

    # ======================================================
    # THREAD → UI SAFE HANDOFF
    # ======================================================

    def _process_images_thread(self, image_paths: list[str]):
        try:
            result = process_paths(
                image_paths,
                log=self._thread_log,
                progress_update=lambda i, t, label: self._thread_progress(i, t, label),
            )
            self._root.after(0, self._on_pipeline_success, result)
        except Exception as e:
            self._root.after(0, self._on_pipeline_error, e)

    def _thread_log(self, msg: str):
        self._root.after(0, self._log, msg)

    def _thread_progress(self, current: int, total: int, label: str):
        # Never allow uninitialized/invalid total
        try:
            t = max(1, int(total))
        except Exception:
            t = 1
        try:
            c = max(0, min(int(current), t))
        except Exception:
            c = 0

        def _ui():
            pct = int((c / t) * 100)
            self._progress["value"] = pct
            self._status.config(text=f"{c}/{t}  {label}")

        self._root.after(0, _ui)

    # ======================================================
    # MAIN THREAD CALLBACKS
    # ======================================================

    def _on_pipeline_success(self, result):
        self._progress["value"] = 100
        self._status.config(text="Complete")

        self._log("Image pipeline complete.")
        self._log(f"Images processed: {getattr(result, 'processed_count', 'UNKNOWN')}")
        self._log(f"Errors: {getattr(result, 'error_count', 'UNKNOWN')}")

        out_dirs = []
        if hasattr(result, "output_dirs") and result.output_dirs:
            out_dirs = [str(p) for p in result.output_dirs]
        elif hasattr(result, "output_dir") and getattr(result, "output_dir"):
            out_dirs = [str(getattr(result, "output_dir"))]

        if out_dirs:
            self._log("Output folders:")
            for d in out_dirs:
                self._log(f"  - {d}")

        self._refresh_staging_stats()

        messagebox.showinfo("Pipeline Complete", "Staging images processed successfully.")

    def _on_pipeline_error(self, error: Exception):
        self._status.config(text="Error")
        self._log(f"PIPELINE ERROR: {error}")
        messagebox.showerror("Pipeline Error", str(error))