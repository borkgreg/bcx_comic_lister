import sys
import subprocess
from pathlib import Path
from tkinter import ttk, messagebox


class CLZScraperTab:
    """Helper tab for launching the CLZ WebView scraper (PyQt).

    - Bundled .app: launch the same executable with `--run-clz-scraper`
    - Source mode: run `python app.py --run-clz-scraper`
    """

    def __init__(self, parent, log):
        self._frame = ttk.Frame(parent)
        self._log = log
        self._build_ui()

    def frame(self):
        return self._frame

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        ttk.Label(
            self._frame,
            text="CLZ WebView Scraper (PyQt)",
            font=("Helvetica", 14, "bold"),
        ).pack(anchor="w", **pad)

        ttk.Label(
            self._frame,
            text="Launches the CLZ scraper in a separate process.",
            justify="left",
        ).pack(anchor="w", **pad)

        ttk.Button(
            self._frame,
            text="Open CLZ WebView Scraper",
            command=self._open_clz_scraper,
        ).pack(anchor="w", **pad)

    def _open_clz_scraper(self):
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--run-clz-scraper"]
                cwd = None
            else:
                project_root = Path(__file__).resolve().parents[2]
                app_py = project_root / "app.py"
                cmd = [sys.executable, str(app_py), "--run-clz-scraper"]
                cwd = str(project_root)

            subprocess.Popen(cmd, cwd=cwd)
            self._log("Launched CLZ WebView Scraper.")
        except Exception as e:
            self._log(f"ERROR launching CLZ Scraper: {e}")
            messagebox.showerror("Launch Error", str(e))
