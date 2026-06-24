"""Minimal one-window Tkinter GUI for the image culler.

Phase 0: Choose a folder, hit Start, watch a progress bar, see a done summary.
Detection is not wired in yet — Start copies every image into ``selects/``.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import core

_WINDOW_TITLE = "Image Culler"
_POLL_MS = 100


class CullerApp:
    """A single window driving the Phase 0 copy-through pipeline.

    AIDEV-NOTE: Tkinter is not thread-safe — only the main thread may touch
    widgets. The worker thread therefore reports progress onto a queue.Queue,
    and the UI drains that queue on the Tk event loop via root.after().
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.folder: Path | None = None
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        root.title(_WINDOW_TITLE)
        root.geometry("460x200")
        root.resizable(False, False)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        self.choose_btn = ttk.Button(
            frame, text="Choose folder...", command=self._choose_folder
        )
        self.choose_btn.pack(fill="x")

        self.folder_label = ttk.Label(
            frame, text="No folder chosen", wraplength=420, foreground="#666"
        )
        self.folder_label.pack(fill="x", pady=(8, 12))

        self.start_btn = ttk.Button(
            frame, text="Start", command=self._start, state="disabled"
        )
        self.start_btn.pack(fill="x")

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill="x", pady=(12, 6))

        self.status_label = ttk.Label(frame, text="")
        self.status_label.pack(fill="x")

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Choose a folder of photos")
        if not chosen:
            return
        self.folder = Path(chosen)
        self.folder_label.config(text=str(self.folder), foreground="#000")
        self.start_btn.config(state="normal")
        self.status_label.config(text="")
        self.progress.config(value=0)

    def _start(self) -> None:
        if self.folder is None or self.worker is not None:
            return
        self.choose_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.status_label.config(text="Scanning...")
        self.progress.config(value=0)

        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()
        self.root.after(_POLL_MS, self._poll_queue)

    def _run(self) -> None:
        """Runs on the worker thread. Never touches widgets directly."""
        folder = self.folder
        assert folder is not None
        try:
            def on_progress(done: int, total: int, _path: Path) -> None:
                self.events.put(("progress", done, total))

            summary = core.process_folder(folder, on_progress)
            self.events.put(("done", summary))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as text
            self.events.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

        if self.worker is not None and self.worker.is_alive():
            self.root.after(_POLL_MS, self._poll_queue)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "progress":
            _, done, total = event
            self.progress.config(maximum=max(total, 1), value=done)
            self.status_label.config(text=f"Analyzing {done} of {total}...")
        elif kind == "done":
            _, summary = event
            self.progress.config(maximum=max(summary.total, 1), value=summary.total)
            if summary.total == 0:
                self.status_label.config(text="No images found in that folder.")
            else:
                text = (
                    f"Done: {summary.kept} keepers to selects/, "
                    f"{summary.rejected} flagged. See report.csv."
                )
                if not summary.blink_used:
                    text += " (blink check unavailable)"
                self.status_label.config(text=text)
            self._finish()
        elif kind == "error":
            _, message = event
            self.status_label.config(text=f"Could not finish: {message}")
            self._finish()

    def _finish(self) -> None:
        self.worker = None
        self.choose_btn.config(state="normal")
        self.start_btn.config(state="normal")


def main() -> None:
    root = tk.Tk()
    CullerApp(root)
    root.mainloop()
