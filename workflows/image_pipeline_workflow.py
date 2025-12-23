from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Iterable, Optional

from core.image_pipeline_core import (
    WatchController,
    default_base_dir,
    open_folder_in_finder,
    process_paths,
    PipelineRunResult,
)


class ImagePipelineWorkflow:
    """
    GUI-friendly wrapper that runs processing in background threads.
    """
    def __init__(self, log: Optional[Callable[[str], None]] = None):
        self.log = log
        self.base_dir = default_base_dir()
        self.input_dir = self.base_dir / "input"
        self.output_root = self.base_dir / "output"
        self.report_dir = self.base_dir / "reports"
        self.watch = WatchController()

    def run_async(
        self,
        paths: Iterable[str],
        on_done: Callable[[PipelineRunResult], None],
    ):
        def _worker():
            result = process_paths(
                paths,
                base_dir=self.base_dir,
                output_root=self.output_root,
                report_dir=self.report_dir,
                log=self.log,
            )
            on_done(result)

        threading.Thread(target=_worker, daemon=True).start()

    def open_output_root(self):
        open_folder_in_finder(self.output_root)

    def start_watch_mode(self, on_new_file_process_done: Optional[Callable[[PipelineRunResult], None]] = None):
        def _on_new_file(path: str):
            # Process just the one new file
            result = process_paths(
                [path],
                base_dir=self.base_dir,
                output_root=self.output_root,
                report_dir=self.report_dir,
                log=self.log,
            )
            if on_new_file_process_done:
                on_new_file_process_done(result)

        self.watch.start(self.input_dir, _on_new_file, log=self.log)

    def stop_watch_mode(self):
        self.watch.stop(log=self.log)