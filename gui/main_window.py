from __future__ import annotations

import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from urllib.parse import urlparse, unquote
import os
import inspect
from datetime import datetime

from workflows.ebay_csv_workflow import run_ebay_csv_workflow
from core.image_pipeline_core import process_paths

try:
    from core.paths import ensure_all_dirs, staging_root_dir, processed_root_dir
    ensure_all_dirs()
    STAGING_ROOT = staging_root_dir(prefer_legacy=True)
    PROCESSED_ROOT = processed_root_dir(prefer_legacy=True)
except Exception:
    STAGING_ROOT = Path.home() / "BCX" / "staging" / "clz_images"
    PROCESSED_ROOT = Path.home() / "BCX" / "processed"
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)

VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class BCXMainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BCX Comic Lister")
        self.root.geometry("1180x740")
        self.root.minsize(1080, 680)

        self.clz_csv_path = ""
        self.output_dir = ""
        self.template_csv_path = str(
            Path(__file__).resolve().parents[1] / "resources" / "ebay_category_template.csv"
        )

        self.hosted_image_urls: list[str] = []
        self.log_text: tk.Text | None = None
        self._scraper_proc: subprocess.Popen | None = None
        self._pipeline_total = 0

        self.status_var = tk.StringVar(value="Ready.")
        self._apply_style()

        self._build_ui()
        self._log_startup_env()
        self._refresh_staging_stats()

    def run(self):
        self.root.mainloop()

    # ==========================================================
    # LOOK & FEEL
    # ==========================================================

    def _apply_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Slightly better scaling on retina / mac
        try:
            self.root.tk.call("tk", "scaling", 1.15)
        except Exception:
            pass

        # Base typography
        self.FONT_H1 = ("Helvetica", 18, "bold")
        self.FONT_H2 = ("Helvetica", 13, "bold")
        self.FONT_BODY = ("Helvetica", 12)
        self.FONT_MUTED = ("Helvetica", 11)

        # Core widget styling (ttk is limited on macOS, but this still helps)
        style.configure("TFrame", padding=0)
        style.configure("Card.TFrame", padding=14)
        style.configure("TLabel", font=self.FONT_BODY)
        style.configure("Muted.TLabel", font=self.FONT_MUTED, foreground="#666666")
        style.configure("H2.TLabel", font=self.FONT_H2)
        style.configure("H1.TLabel", font=self.FONT_H1)

        style.configure("TButton", padding=(12, 8))
        style.configure("Primary.TButton", padding=(14, 10))
        style.map(
            "Primary.TButton",
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )

        style.configure("Small.TButton", padding=(10, 6))
        style.configure("TEntry", padding=(8, 6))

    # ==========================================================
    # UI LAYOUT
    # ==========================================================

    def _build_ui(self):
        outer = ttk.Panedwindow(self.root, orient="horizontal")
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        right = ttk.Frame(outer)
        outer.add(left, weight=3)
        outer.add(right, weight=2)

        # ---- Scrollable left flow ----
        self._left_canvas = tk.Canvas(left, highlightthickness=0)
        self._left_scrollbar = ttk.Scrollbar(left, orient="vertical", command=self._left_canvas.yview)
        self.flow = ttk.Frame(self._left_canvas)

        self.flow.bind("<Configure>", self._on_flow_configure)
        self._left_canvas.bind("<Configure>", self._on_canvas_configure)

        self._left_canvas_window = self._left_canvas.create_window((0, 0), window=self.flow, anchor="nw")
        self._left_canvas.configure(yscrollcommand=self._left_scrollbar.set)

        self._left_canvas.pack(side="left", fill="both", expand=True)
        self._left_scrollbar.pack(side="right", fill="y")

        self._bind_mousewheel(left, self._left_canvas)

        # ---- Header (left) ----
        self._section_header(self.flow)

        # Sections
        self._section_inputs(self.flow)
        self._section_scraper(self.flow)
        self._section_pipeline(self.flow)
        self._section_urls(self.flow)
        self._section_export(self.flow)

        # ---- Right log + controls ----
        header_row = ttk.Frame(right)
        header_row.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(header_row, text="Activity Log", style="H2.TLabel").pack(side="left")
        ttk.Button(header_row, text="Copy", style="Small.TButton", command=self._copy_log).pack(side="right")
        ttk.Button(header_row, text="Clear", style="Small.TButton", command=self._clear_log).pack(side="right", padx=(0, 8))

        self.log_text = tk.Text(right, height=20, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # ---- Status bar ----
        status = ttk.Frame(self.root)
        status.pack(fill="x", side="bottom")
        ttk.Separator(status, orient="horizontal").pack(fill="x")
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", padx=12, pady=6)

    def _section_header(self, parent):
        wrap = ttk.Frame(parent, padding=(16, 14))
        wrap.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(wrap, text="BCX Comic Lister", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            wrap,
            text="Download → Stage → Enhance → Export eBay CSV (fast + repeatable).",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        btns = ttk.Frame(wrap)
        btns.pack(anchor="w", pady=(12, 0))

        ttk.Button(btns, text="📁 Open Staging", style="Small.TButton", command=lambda: self._reveal_path(STAGING_ROOT)).pack(side="left")
        ttk.Button(btns, text="📁 Open Processed", style="Small.TButton", command=lambda: self._reveal_path(PROCESSED_ROOT)).pack(side="left", padx=8)
        ttk.Button(btns, text="🧾 Open Output Folder", style="Small.TButton", command=self._open_output_folder).pack(side="left")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=12, pady=(6, 6))

    def _open_output_folder(self):
        if self.output_dir:
            self._reveal_path(Path(self.output_dir))
        else:
            messagebox.showinfo("No Output Folder", "Choose an output folder first in Inputs.")
            self._set_status("Pick an output folder first.")

    def _on_flow_configure(self, _e):
        try:
            self._left_canvas.configure(scrollregion=self._left_canvas.bbox("all"))
        except Exception:
            pass

    def _on_canvas_configure(self, e):
        try:
            self._left_canvas.itemconfigure(self._left_canvas_window, width=e.width)
        except Exception:
            pass

    def _bind_mousewheel(self, widget, canvas: tk.Canvas):
        def _on_mousewheel(event):
            try:
                delta = event.delta
                if delta == 0:
                    return
                step = -1 if delta > 0 else 1
                canvas.yview_scroll(step, "units")
            except Exception:
                pass

        def _on_linux_scroll_up(_event):
            canvas.yview_scroll(-1, "units")

        def _on_linux_scroll_down(_event):
            canvas.yview_scroll(1, "units")

        widget.bind_all("<MouseWheel>", _on_mousewheel)
        widget.bind_all("<Button-4>", _on_linux_scroll_up)
        widget.bind_all("<Button-5>", _on_linux_scroll_down)

    def _card(self, parent, title: str, subtitle: str | None = None):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.pack(fill="x", padx=12, pady=10)

        top = ttk.Frame(frame)
        top.pack(fill="x")

        ttk.Label(top, text=title, style="H2.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(frame, text=subtitle, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(6, 0))
        return frame

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    def _reveal_path(self, path: Path):
        try:
            p = str(path)
            if sys.platform == "darwin":
                subprocess.Popen(["open", p])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", p])
            else:
                subprocess.Popen(["xdg-open", p])
            self._set_status(f"Opened: {p}")
        except Exception as e:
            messagebox.showerror("Open Folder Error", str(e))

    # ==========================================================
    # 1) INPUTS
    # ==========================================================

    def _section_inputs(self, parent):
        card = self._card(parent, "1) Inputs", "Choose your CLZ export + where to save the CSV files.")

        row = ttk.Frame(card)
        row.pack(fill="x", pady=(12, 0))
        row.columnconfigure(1, weight=1)

        ttk.Button(row, text="📄 Select CLZ Export CSV", style="Small.TButton", command=self._select_clz_csv).grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.lbl_clz = ttk.Label(row, text="Not selected", style="Muted.TLabel")
        self.lbl_clz.grid(row=0, column=1, sticky="w")

        ttk.Button(row, text="📁 Select Output Folder", style="Small.TButton", command=self._select_output_dir).grid(row=1, column=0, padx=(0, 10), pady=(10, 0), sticky="w")
        self.lbl_output = ttk.Label(row, text="Not selected", style="Muted.TLabel")
        self.lbl_output.grid(row=1, column=1, sticky="w", pady=(10, 0))

    def _select_clz_csv(self):
        path = filedialog.askopenfilename(
            title="Select CLZ Export CSV",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if path:
            self.clz_csv_path = path
            self.lbl_clz.config(text=os.path.basename(path))
            self._log(f"Selected CLZ export: {path}")
            self._set_status("CLZ export selected.")

    def _select_output_dir(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_dir = path
            self.lbl_output.config(text=path)
            self._log(f"Selected output dir: {path}")
            self._set_status("Output folder selected.")

    # ==========================================================
    # 2) SCRAPER
    # ==========================================================

    def _section_scraper(self, parent):
        card = self._card(
            parent,
            "2) Download covers from CLZ",
            "Opens the CLZ WebView scraper in a separate window. Downloads go into staging.",
        )
        ttk.Label(card, text=f"Staging: {STAGING_ROOT}", style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

        btn_row = ttk.Frame(card)
        btn_row.pack(anchor="w", pady=(12, 0))

        ttk.Button(btn_row, text="🌐 Open CLZ Scraper", style="Primary.TButton", command=self._open_clz_scraper).pack(side="left")
        ttk.Button(btn_row, text="↻ Refresh Stats", style="Small.TButton", command=self._refresh_staging_stats).pack(side="left", padx=10)
        ttk.Button(btn_row, text="🧹 Clear Staged", style="Small.TButton", command=self._clear_staged).pack(side="left")

        self.lbl_staging_stats = ttk.Label(card, text="(loading...)", style="Muted.TLabel")
        self.lbl_staging_stats.pack(anchor="w", pady=(10, 0))

    def _open_clz_scraper(self):
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--run-clz-scraper"]
                cwd = None
            else:
                project_root = Path(__file__).resolve().parents[1]
                app_py = project_root / "app.py"
                cmd = [sys.executable, str(app_py), "--run-clz-scraper"]
                cwd = str(project_root)

            self._log(f"Launching scraper: {' '.join(cmd)}")
            self._set_status("Launching CLZ scraper…")

            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._scraper_proc = proc

            self._log("Launched CLZ WebView Scraper.")
            if proc.stdout:
                threading.Thread(target=self._stream_pipe_to_log, args=(proc.stdout, "[SCRAPER] "), daemon=True).start()
            if proc.stderr:
                threading.Thread(target=self._stream_pipe_to_log, args=(proc.stderr, "[SCRAPER:ERR] "), daemon=True).start()

            threading.Thread(target=self._watch_process_exit, args=(proc,), daemon=True).start()

        except Exception as e:
            self._log(f"ERROR launching CLZ Scraper: {e}")
            self._set_status("Error launching scraper.")
            messagebox.showerror("Launch Error", str(e))

    def _stream_pipe_to_log(self, pipe, prefix: str):
        try:
            for line in iter(pipe.readline, ""):
                if not line:
                    break
                self._log_threadsafe(prefix + line.rstrip("\n"))
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _watch_process_exit(self, proc: subprocess.Popen):
        try:
            code = proc.wait()
            self._log_threadsafe(f"[SCRAPER] process exited with code {code}")
            self._log_threadsafe("Tip: click “Refresh Stats” after downloads.")
            self.root.after(0, lambda: self._set_status("Scraper closed. Refresh stats when ready."))
        except Exception as e:
            self._log_threadsafe(f"[SCRAPER] process wait error: {e}")

    def _log_threadsafe(self, msg: str):
        try:
            self.root.after(0, self._log, msg)
        except Exception:
            pass

    # ---------- staging helpers ----------
    def _gather_staging_images(self) -> list[str]:
        if not STAGING_ROOT.exists():
            return []
        return [str(p) for p in STAGING_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in VALID_EXTS]

    def _refresh_staging_stats(self):
        img_count = 0
        series_count = 0
        try:
            paths = self._gather_staging_images()
            img_count = len(paths)

            series_folders = set()
            for raw in paths:
                p = Path(raw)
                try:
                    rel = p.relative_to(STAGING_ROOT)
                    if len(rel.parts) >= 2:
                        series_folders.add(rel.parts[0])
                except Exception:
                    pass
            series_count = len(series_folders)

            if series_count > 0:
                txt = f"Staged images: {img_count}   •   Series folders: {series_count}"
            else:
                txt = f"Staged images: {img_count}"

            self.lbl_staging_stats.config(text=txt)
            self._set_status("Staging stats refreshed.")

        except Exception as e:
            self.lbl_staging_stats.config(text=f"Error reading staging folder: {e}")
            self._set_status("Error refreshing staging stats.")

    def _clear_staged(self):
        if not STAGING_ROOT.exists():
            messagebox.showinfo("Nothing to clear", f"Staging folder not found:\n{STAGING_ROOT}")
            return

        paths = self._gather_staging_images()
        if not paths:
            messagebox.showinfo("Nothing to clear", "No staged images found.")
            return

        ok = messagebox.askyesno(
            "Clear Staged Images",
            f"This will permanently delete {len(paths)} staged image file(s)\n"
            f"inside:\n{STAGING_ROOT}\n\nContinue?",
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

        # Remove empty folders (keep root)
        try:
            for d in sorted([p for p in STAGING_ROOT.rglob("*") if p.is_dir()], reverse=True):
                try:
                    if d != STAGING_ROOT and not any(d.iterdir()):
                        d.rmdir()
                except Exception:
                    pass
        except Exception:
            pass

        self._log(f"Clear Staged: deleted={deleted} errors={errors}")
        self._refresh_staging_stats()
        self._set_status("Staged images cleared.")
        messagebox.showinfo("Clear Staged", f"Deleted: {deleted}\nErrors: {errors}")

    # ==========================================================
    # 3) PIPELINE
    # ==========================================================

    def _section_pipeline(self, parent):
        card = self._card(
            parent,
            "3) Enhance staged images",
            "Processes ALL images in staging (including subfolders) and writes enhanced images into processed.",
        )
        ttk.Label(card, text=f"Processed: {PROCESSED_ROOT}", style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

        btn_row = ttk.Frame(card)
        btn_row.pack(anchor="w", pady=(12, 0))
        ttk.Button(btn_row, text="✨ Process Staged Images", style="Primary.TButton", command=self._run_pipeline).pack(side="left")

        self.pipeline_status = ttk.Label(card, text="Idle", style="Muted.TLabel")
        self.pipeline_status.pack(anchor="w", pady=(12, 0))

        self.pipeline_progress = ttk.Progressbar(card, orient="horizontal", mode="determinate", length=520)
        self.pipeline_progress.pack(anchor="w", pady=(6, 0))

    def _run_pipeline(self):
        paths = self._gather_staging_images()
        if not paths:
            messagebox.showinfo("No images", "No images found in the staging folder.")
            return

        self._pipeline_total = len(paths)
        self.pipeline_progress["value"] = 0
        self.pipeline_status.config(text=f"0/{self._pipeline_total} Starting…")
        self._log(f"Starting image pipeline on {self._pipeline_total} images.")
        self._set_status("Processing staged images…")

        threading.Thread(target=self._pipeline_thread, args=(paths,), daemon=True).start()

    def _pipeline_thread(self, paths: list[str]):
        try:
            result = process_paths(
                paths,
                log=lambda m: self._log_threadsafe(m),
                progress_update=lambda i, t, label: self._pipeline_progress_threadsafe(i, t, label),
            )
            self.root.after(0, self._on_pipeline_done, result)
        except Exception as e:
            self.root.after(0, self._on_pipeline_error, e)

    def _pipeline_progress_threadsafe(self, current: int, total: int, label: str):
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
            self.pipeline_progress["value"] = pct
            self.pipeline_status.config(text=f"{c}/{t}  {label}")

        self.root.after(0, _ui)

    def _on_pipeline_done(self, result):
        self.pipeline_progress["value"] = 100
        self.pipeline_status.config(text="Complete")
        self._log("Image pipeline complete.")
        self._log(f"Images processed: {result.processed_count}")
        self._log(f"Errors: {result.error_count}")
        if getattr(result, "output_dirs", None):
            self._log("Output folders:")
            for d in result.output_dirs:
                self._log(f"  - {d}")
        self._refresh_staging_stats()
        self._set_status("Pipeline complete.")
        messagebox.showinfo("Pipeline Complete", "Staging images processed successfully.")

    def _on_pipeline_error(self, error: Exception):
        self.pipeline_status.config(text="Error")
        self._log(f"PIPELINE ERROR: {error}")
        self._set_status("Pipeline error.")
        messagebox.showerror("Pipeline Error", str(error))

    # ==========================================================
    # 4) HOSTED URLS
    # ==========================================================

    def _section_urls(self, parent):
        card = self._card(
            parent,
            "4) Hosted image URLs",
            "Paste hosted image URLs (one per line). Filenames must follow BCX rules.",
        )

        self.urls_text = tk.Text(card, height=10, wrap="none")
        self.urls_text.pack(fill="x", expand=False, pady=(12, 0))

        btn_row = ttk.Frame(card)
        btn_row.pack(anchor="w", pady=(12, 0))

        ttk.Button(btn_row, text="🔍 Validate URLs", style="Small.TButton", command=self._process_hosted_urls).pack(side="left")
        ttk.Button(btn_row, text="🧽 Clear URLs", style="Small.TButton", command=self._clear_urls).pack(side="left", padx=10)

        self.lbl_url_status = ttk.Label(card, text="Not processed", style="Muted.TLabel")
        self.lbl_url_status.pack(anchor="w", pady=(10, 0))

    def _clear_urls(self):
        try:
            self.urls_text.delete("1.0", "end")
        except Exception:
            pass
        self.hosted_image_urls = []
        self.lbl_url_status.config(text="Cleared.")
        self._log("Hosted URLs cleared.")
        self._set_status("Hosted URLs cleared.")

    def _process_hosted_urls(self):
        from core.image_allocator import parse_image_filename

        raw = self.urls_text.get("1.0", "end").strip()
        if not raw:
            self.hosted_image_urls = []
            self.lbl_url_status.config(text="No URLs pasted.")
            self._set_status("No URLs pasted.")
            return

        accepted = rejected = deduped = 0
        urls: list[str] = []
        seen = set()

        for line in raw.splitlines():
            url = line.strip()
            if not url:
                continue
            if url in seen:
                deduped += 1
                continue

            parsed = urlparse(url)
            filename = Path(unquote(parsed.path)).name
            if not filename:
                rejected += 1
                continue

            p = Path(filename)
            if p.stem.lower().endswith("-vi"):
                filename = f"{p.stem[:-3]}{p.suffix}"

            if not parse_image_filename(filename):
                rejected += 1
                continue

            urls.append(url)
            seen.add(url)
            accepted += 1

        self.hosted_image_urls = urls
        msg = f"Accepted {accepted} • Rejected {rejected} • Duplicates ignored {deduped}"
        self.lbl_url_status.config(text=msg)
        self._log(msg)
        self._set_status("Hosted URLs validated.")

    # ==========================================================
    # 5) EXPORT
    # ==========================================================

    def _section_export(self, parent):
        card = self._card(
            parent,
            "5) Export eBay CSV",
            "Generates ebay_ready.csv + failed.csv using CLZ export + hosted URLs.",
        )

        row = ttk.Frame(card)
        row.pack(anchor="w", pady=(12, 0))

        ttk.Label(row, text="Minimum Start Price:", style="Muted.TLabel").pack(side="left")
        self.min_price_var = tk.StringVar(value="3.00")
        ttk.Entry(row, width=10, textvariable=self.min_price_var).pack(side="left", padx=10)
        ttk.Label(row, text="(blanks + values below this will be raised)", style="Muted.TLabel").pack(side="left")

        ttk.Button(card, text="🚀 Run eBay CSV Export", style="Primary.TButton", command=self._run_workflow).pack(anchor="w", pady=(14, 0))

    def _parse_min_price(self):
        s = (self.min_price_var.get() or "").strip()
        if not s:
            return None
        s = s.replace("$", "").replace(",", "").strip()
        try:
            return float(s)
        except Exception:
            return None

    def _run_workflow(self):
        if not self.clz_csv_path:
            messagebox.showerror("Missing Input", "Select a CLZ CSV.")
            return
        if not self.output_dir:
            messagebox.showerror("Missing Output Folder", "Select an output folder.")
            return
        if not self.hosted_image_urls:
            messagebox.showerror("Missing Hosted URLs", "Paste and validate hosted URLs first.")
            return

        min_price = self._parse_min_price()
        if self.min_price_var.get().strip() and min_price is None:
            messagebox.showerror("Invalid Minimum Price", "Enter a number like 3.00 (or leave blank).")
            return

        self._log("Starting eBay CSV export…")
        self._set_status("Exporting eBay CSV…")

        try:
            sig = inspect.signature(run_ebay_csv_workflow)
            params = sig.parameters

            kwargs = dict(
                clz_csv_path=self.clz_csv_path,
                ebay_template_csv_path=self.template_csv_path,
                output_dir=self.output_dir,
            )

            if "min_start_price" in params:
                kwargs["min_start_price"] = min_price

            if "hosted_image_urls" in params:
                kwargs["hosted_image_urls"] = self.hosted_image_urls
            elif "hosted_image_urls_by_image_id" in params:
                kwargs["image_paths"] = []
                kwargs["hosted_image_urls_by_image_id"] = {"HOSTED": self.hosted_image_urls}
            else:
                raise TypeError(
                    "run_ebay_csv_workflow has an unexpected signature; "
                    "expected hosted_image_urls or hosted_image_urls_by_image_id."
                )

            result = run_ebay_csv_workflow(**kwargs)

        except Exception as e:
            self._log(f"ERROR: {e}")
            self._set_status("Export error.")
            messagebox.showerror("Workflow Error", str(e))
            return

        self._log("CSV export complete.")
        if isinstance(result, dict):
            for k in ("total_clz_rows", "images_parsed", "comics_matched", "comics_failed", "unused_image_urls"):
                if k in result:
                    self._log(f"{k}: {result[k]}")

        self._set_status("Export complete.")
        messagebox.showinfo("Done", "eBay CSVs generated successfully.")

    # ==========================================================
    # LOGGING
    # ==========================================================

    def _copy_log(self):
        if not self.log_text:
            return
        try:
            data = self.log_text.get("1.0", "end")
            self.root.clipboard_clear()
            self.root.clipboard_append(data)
            self._set_status("Log copied to clipboard.")
        except Exception:
            pass

    def _clear_log(self):
        if not self.log_text:
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._set_status("Log cleared.")

    def _log(self, msg: str):
        if not self.log_text:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_startup_env(self):
        frozen = getattr(sys, "frozen", False)
        self._log(f"Startup: frozen={frozen}")
        self._log(f"sys.executable: {sys.executable}")
        try:
            self._log(f"cwd: {os.getcwd()}")
        except Exception:
            pass
        self._log(f"Staging root: {STAGING_ROOT}")
        self._log(f"Processed root: {PROCESSED_ROOT}")
        self._set_status("Ready.")