import sys
import os
import traceback
from pathlib import Path
import importlib.util

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
    QProgressBar,
    QLabel,
)
from PyQt5.QtCore import QUrl, QObject, QThread, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage

try:
    from core.paths import logs_dir, staging_root_dir, web_profile_dir
except Exception:
    def logs_dir() -> Path:
        d = Path.home() / "Library" / "Logs" / "BCX"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def staging_root_dir(*, prefer_legacy: bool = True) -> Path:
        d = Path.home() / "BCX" / "staging" / "clz_images"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def web_profile_dir(*, prefer_legacy: bool = True) -> Path:
        d = Path.home() / "Library" / "Application Support" / "BCX Comic Lister" / "clz_web_profile"
        d.mkdir(parents=True, exist_ok=True)
        return d


LOG_DIR = logs_dir()
LOG_FILE = LOG_DIR / "clz_scraper.log"


def log(msg: str):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
            f.flush()
    except Exception:
        pass


def _spec_origin(modname: str) -> str:
    try:
        spec = importlib.util.find_spec(modname)
        if not spec:
            return "NOT_FOUND"
        origin = getattr(spec, "origin", None)
        if origin:
            return str(origin)
        locs = getattr(spec, "submodule_search_locations", None)
        if locs:
            return ",".join([str(x) for x in locs])
        return "FOUND_NO_ORIGIN"
    except Exception as e:
        return f"ERROR({e})"


def startup_self_check():
    try:
        frozen = getattr(sys, "frozen", False)
        meipass = getattr(sys, "_MEIPASS", None)

        log("--- SELF CHECK ---")
        log(f"python_version: {sys.version.replace(os.linesep, ' ')}")
        log(f"frozen: {frozen}")
        log(f"sys.executable: {sys.executable}")
        log(f"cwd: {os.getcwd()}")
        if meipass:
            log(f"sys._MEIPASS: {meipass}")

        for i, p in enumerate(sys.path[:10]):
            log(f"sys.path[{i}]: {p}")

        log(f"spec tools.clz_scraper.downloader: {_spec_origin('tools.clz_scraper.downloader')}")
        log(f"spec tools.clz_scraper.utils: {_spec_origin('tools.clz_scraper.utils')}")
        log(f"spec requests: {_spec_origin('requests')}")
        log(f"spec PyQt5.QtWebEngineWidgets: {_spec_origin('PyQt5.QtWebEngineWidgets')}")
        log("--- SELF CHECK END ---")
    except Exception:
        log("SELF CHECK ERROR:")
        log(traceback.format_exc())


startup_self_check()

try:
    from tools.clz_scraper.downloader import download_comics
except Exception:
    BASE_DIR = Path(__file__).parent
    sys.path.insert(0, str(BASE_DIR))
    from downloader import download_comics  # type: ignore


CLZ_URL = "https://cloud.collectorz.com/comics"

STAGING_ROOT = staging_root_dir(prefer_legacy=True)
STAGING_ROOT.mkdir(parents=True, exist_ok=True)

PROFILE_ROOT = web_profile_dir(prefer_legacy=True)
PROFILE_STORAGE = PROFILE_ROOT / "storage"
PROFILE_CACHE = PROFILE_ROOT / "cache"
PROFILE_STORAGE.mkdir(parents=True, exist_ok=True)
PROFILE_CACHE.mkdir(parents=True, exist_ok=True)


SCRAPER_JS = r"""
(function () {
    try {
        const handler = window.SelectableHandler || window.$4 || null;
        if (!handler) {
            return { error: "Selectable handler not found." };
        }

        const selected = handler.getSelectedCollectionItems();
        const results = [];

        selected.each(function () {
            const el = this;

            const titleEl = el.querySelector(".placeholder-text .title");
            const issueEl = el.querySelector(".placeholder-text .subtitle");
            const imgEl = el.querySelector("img");
            const sourceEl = el.querySelector("picture source[type='image/webp']");

            const series = titleEl ? titleEl.textContent.trim() : "";
            const issue = issueEl ? issueEl.textContent.trim() : "";

            let image = "";

            function upgrade(url) {
                if (!url) return "";
                url = url.split(" ")[0];
                url = url.replace("/md/2x/", "/lg/").replace("/md/", "/lg/");
                if (url.endsWith(".jpg")) {
                    url = url.replace(".jpg", ".webp");
                }
                return url;
            }

            if (sourceEl) {
                image = upgrade(sourceEl.getAttribute("data-srcset") || "");
            } else if (imgEl) {
                image = upgrade(imgEl.getAttribute("data-src") || imgEl.getAttribute("src") || "");
            }

            results.push({
                series: series,
                issue: issue,
                image: image
            });
        });

        return { items: results };
    } catch (e) {
        return { error: String(e) };
    }
})();
"""


class DownloadWorker(QObject):
    progress = pyqtSignal(int, int, str)      # current, total, label
    log_line = pyqtSignal(str)
    finished = pyqtSignal(int, int)           # downloaded, skipped
    failed = pyqtSignal(str)

    def __init__(self, items, staging_root: Path):
        super().__init__()
        self._items = items
        self._staging_root = staging_root

    def run(self):
        try:
            downloaded, skipped = download_comics(
                self._items,
                self._staging_root,
                progress_callback=lambda m: self.log_line.emit(m),
                progress_update=lambda i, t, lbl: self.progress.emit(i, t, lbl),
            )
            self.finished.emit(downloaded, skipped)
        except Exception as e:
            self.failed.emit(str(e))


class CLZScraperWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CLZ WebView Scraper")
        self.resize(1200, 820)

        self._thread: QThread | None = None
        self._worker: DownloadWorker | None = None

        central = QWidget()
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.btn_download = QPushButton("Download Selected Covers")
        self.btn_download.clicked.connect(self.run_scraper)
        top.addWidget(self.btn_download)

        self.btn_clear_session = QPushButton("Clear Login Session")
        self.btn_clear_session.clicked.connect(self.clear_session)
        top.addWidget(self.btn_clear_session)

        top.addStretch(1)
        layout.addLayout(top)

        prog_row = QHBoxLayout()
        self.progress_label = QLabel("Ready.")
        self.progress_label.setMinimumWidth(260)
        prog_row.addWidget(self.progress_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        prog_row.addWidget(self.progress, stretch=1)
        layout.addLayout(prog_row)

        self.profile = QWebEngineProfile("BCX_CLZ_PROFILE", self)
        self.profile.setPersistentStoragePath(str(PROFILE_STORAGE))
        self.profile.setCachePath(str(PROFILE_CACHE))
        self.profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        self.web = QWebEngineView()
        self.web.setPage(QWebEnginePage(self.profile, self.web))
        self.web.setUrl(QUrl(CLZ_URL))
        layout.addWidget(self.web)

        self.setCentralWidget(central)

        log(f"Staging root: {STAGING_ROOT}")
        log(f"Web profile dir: {PROFILE_ROOT}")

    def clear_session(self):
        try:
            try:
                store = self.profile.cookieStore()
                store.deleteAllCookies()
            except Exception:
                pass

            for d in (PROFILE_STORAGE, PROFILE_CACHE):
                if d.exists():
                    for p in sorted(d.rglob("*"), reverse=True):
                        try:
                            if p.is_file() or p.is_symlink():
                                p.unlink()
                            else:
                                p.rmdir()
                        except Exception:
                            pass
                    try:
                        d.rmdir()
                    except Exception:
                        pass

            QMessageBox.information(
                self,
                "Session Cleared",
                "Login session cleared. Restart the scraper window to log in again.",
            )
            log("User cleared login session.")
        except Exception as e:
            log(f"Clear session error: {e}")
            QMessageBox.warning(self, "Error", str(e))

    def run_scraper(self):
        log("Running scraper JS")
        self.web.page().runJavaScript(SCRAPER_JS, self.handle_result)

    def handle_result(self, result):
        if not result or "error" in result:
            QMessageBox.warning(self, "Scraper Error", str(result))
            log(f"Scraper error: {result}")
            return

        items = result.get("items", [])
        if not items:
            QMessageBox.information(self, "No Selection", "No comics selected.")
            return

        log(f"Selected items: {len(items)}")
        self._start_download_thread(items)

    def _start_download_thread(self, items):
        if self._thread is not None:
            QMessageBox.information(self, "Busy", "A download is already running.")
            return

        self.progress.setValue(0)
        self.progress_label.setText("Starting...")
        self.btn_download.setEnabled(False)

        self._thread = QThread()
        self._worker = DownloadWorker(items, STAGING_ROOT)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(lambda s: log(s))
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _cleanup_thread(self):
        self._thread = None
        self._worker = None
        self.btn_download.setEnabled(True)
        self.progress_label.setText("Ready.")

    def _on_progress(self, current: int, total: int, label: str):
        if total <= 0:
            self.progress.setValue(0)
            return
        pct = int((current / total) * 100)
        self.progress.setValue(max(0, min(100, pct)))
        self.progress_label.setText(f"{current}/{total}  {label}")

    def _on_finished(self, downloaded: int, skipped: int):
        log(f"Download complete. Downloaded={downloaded} Skipped={skipped}")
        QMessageBox.information(
            self,
            "Download Complete",
            f"Downloaded: {downloaded}\nSkipped: {skipped}\n\nSaved under:\n{STAGING_ROOT}",
        )

    def _on_failed(self, err: str):
        log(f"Download failed: {err}")
        QMessageBox.warning(self, "Download Error", err)


def main():
    try:
        app = QApplication(sys.argv)
        win = CLZScraperWindow()
        win.show()
        app.exec_()
    except Exception:
        log("FATAL ERROR:")
        log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()