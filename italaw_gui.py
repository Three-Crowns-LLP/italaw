#!/usr/bin/env python3
"""
italaw Investment Arbitration Downloader — Windows GUI

Double-click this file (or run via run.bat) for a simple point-and-click interface.
No command line required.
"""

import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
from pathlib import Path
import logging
import sys

# ---------------------------------------------------------------------------
# Redirect logging into the GUI text box
# ---------------------------------------------------------------------------

class TextHandler(logging.Handler):
    """Logging handler that appends records to a Tkinter ScrolledText widget."""

    def __init__(self, widget: scrolledtext.ScrolledText):
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record) + "\n"
        # Must update the widget from the main thread
        self.widget.after(0, self._append, msg)

    def _append(self, msg: str) -> None:
        self.widget.configure(state="normal")
        self.widget.insert(tk.END, msg)
        self.widget.see(tk.END)
        self.widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("italaw Investment Arbitration Downloader")
        self.resizable(True, True)
        self.minsize(700, 580)

        # Try to set a reasonable initial size
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        w, h = min(820, screen_w - 100), min(700, screen_h - 100)
        self.geometry(f"{w}x{h}+{(screen_w - w)//2}+{(screen_h - h)//2}")

        self._build_ui()
        self._setup_logging()
        self._download_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 5}

        # ---- Header ----
        header = tk.Frame(self, bg="#1a3a5c")
        header.pack(fill="x")
        tk.Label(
            header,
            text="italaw  Investment Arbitration Downloader",
            font=("Segoe UI", 14, "bold"),
            fg="white",
            bg="#1a3a5c",
            pady=12,
        ).pack()
        tk.Label(
            header,
            text="Downloads publicly available PDFs from italaw.com",
            font=("Segoe UI", 9),
            fg="#aac8e8",
            bg="#1a3a5c",
            pady=2,
        ).pack()

        # ---- Options frame ----
        opts = ttk.LabelFrame(self, text="Download options", padding=10)
        opts.pack(fill="x", **pad)
        opts.columnconfigure(1, weight=1)

        # Output directory
        tk.Label(opts, text="Save to folder:", anchor="w").grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.output_var = tk.StringVar(
            value=str(Path.home() / "Documents" / "investment arbitration materials")
        )
        dir_entry = ttk.Entry(opts, textvariable=self.output_var)
        dir_entry.grid(row=0, column=1, sticky="ew", padx=(8, 4))
        ttk.Button(opts, text="Browse…", command=self._choose_dir).grid(
            row=0, column=2, padx=(0, 0)
        )

        # Respondent state filter
        tk.Label(opts, text="Respondent state:", anchor="w").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.state_var = tk.StringVar()
        state_entry = ttk.Entry(opts, textvariable=self.state_var)
        state_entry.grid(row=1, column=1, sticky="ew", padx=(8, 4), columnspan=2)
        tk.Label(
            opts,
            text='Leave blank for all countries  (e.g. type "Argentina" to filter)',
            fg="grey",
            font=("Segoe UI", 8),
        ).grid(row=2, column=1, sticky="w", padx=(8, 0), columnspan=2)

        # Max cases
        tk.Label(opts, text="Max cases:", anchor="w").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self.max_cases_var = tk.StringVar(value="")
        max_entry = ttk.Entry(opts, textvariable=self.max_cases_var, width=10)
        max_entry.grid(row=3, column=1, sticky="w", padx=(8, 4))
        tk.Label(
            opts,
            text="Leave blank to download all cases (may take several hours)",
            fg="grey",
            font=("Segoe UI", 8),
        ).grid(row=4, column=1, sticky="w", padx=(8, 0), columnspan=2)

        # Document types
        tk.Label(opts, text="Document types:", anchor="w").grid(
            row=5, column=0, sticky="w", pady=4
        )
        doc_frame = tk.Frame(opts)
        doc_frame.grid(row=5, column=1, sticky="w", padx=(8, 0), columnspan=2)
        self.chk_vars = {}
        default_types = {
            "Awards & Decisions": True,
            "Procedural Orders": True,
            "Hearing Transcripts": True,
            "Rulings & Judgments": True,
        }
        for label, default in default_types.items():
            var = tk.BooleanVar(value=default)
            self.chk_vars[label] = var
            ttk.Checkbutton(doc_frame, text=label, variable=var).pack(
                side="left", padx=(0, 12)
            )

        # Dry run
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts,
            text="Dry run (list files without downloading)",
            variable=self.dry_run_var,
        ).grid(row=6, column=1, sticky="w", padx=(8, 0), pady=(6, 0), columnspan=2)

        # ---- Buttons ----
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.start_btn = ttk.Button(
            btn_frame,
            text="Start Download",
            command=self._start,
            style="Accent.TButton",
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ttk.Button(
            btn_frame, text="Stop", command=self._stop, state="disabled"
        )
        self.stop_btn.pack(side="left")

        self.open_btn = ttk.Button(
            btn_frame, text="Open output folder", command=self._open_folder
        )
        self.open_btn.pack(side="right")

        # ---- Progress bar ----
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=(0, 4))

        # ---- Log window ----
        log_frame = ttk.LabelFrame(self, text="Progress log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            state="disabled",
            font=("Consolas", 9),
            wrap="word",
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.log_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _choose_dir(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select output folder",
            initialdir=self.output_var.get(),
        )
        if chosen:
            self.output_var.set(chosen)

    def _open_folder(self) -> None:
        folder = Path(self.output_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        import subprocess
        subprocess.Popen(f'explorer "{folder}"')

    def _collect_doc_types(self) -> list[str] | None:
        """Map checkbox labels to the keyword strings used by the downloader."""
        mapping = {
            "Awards & Decisions": ["award", "decision"],
            "Procedural Orders": ["procedural order", "order"],
            "Hearing Transcripts": ["hearing transcript", "transcript"],
            "Rulings & Judgments": ["ruling", "judgment"],
        }
        selected: list[str] = []
        for label, keywords in mapping.items():
            if self.chk_vars[label].get():
                selected.extend(keywords)
        return selected if selected else None

    def _start(self) -> None:
        # Validate inputs
        output_dir = self.output_var.get().strip()
        if not output_dir:
            messagebox.showerror("Error", "Please choose an output folder.")
            return

        max_cases_str = self.max_cases_var.get().strip()
        max_cases: int | None = None
        if max_cases_str:
            try:
                max_cases = int(max_cases_str)
                if max_cases <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Error", "Max cases must be a positive whole number (or leave blank)."
                )
                return

        doc_types = self._collect_doc_types()
        if not doc_types:
            messagebox.showerror(
                "Error", "Please tick at least one document type."
            )
            return

        respondent_state = self.state_var.get().strip() or None
        dry_run = self.dry_run_var.get()

        # Clear log
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")

        # Toggle button states
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start(12)

        # Run download in background thread so the GUI stays responsive
        self._stop_flag = threading.Event()
        self._download_thread = threading.Thread(
            target=self._run_download,
            args=(output_dir, max_cases, respondent_state, doc_types, dry_run),
            daemon=True,
        )
        self._download_thread.start()

    def _stop(self) -> None:
        if hasattr(self, "_stop_flag"):
            self._stop_flag.set()
        self.stop_btn.configure(state="disabled")
        logging.getLogger().info("Stop requested — finishing current download then stopping…")

    def _run_download(
        self,
        output_dir: str,
        max_cases: int | None,
        respondent_state: str | None,
        doc_types: list[str],
        dry_run: bool,
    ) -> None:
        """Runs in a background thread."""
        try:
            # Import here so GUI loads even if dependencies are missing
            from italaw_downloader import run, TARGET_DOC_KEYWORDS
            TARGET_DOC_KEYWORDS.clear()
            TARGET_DOC_KEYWORDS.update(doc_types)

            run(
                max_cases=max_cases,
                respondent_state=respondent_state,
                output_dir=Path(output_dir),
                dry_run=dry_run,
                stop_flag=getattr(self, "_stop_flag", None),
            )
        except ImportError as exc:
            logging.getLogger().error(
                f"Missing dependency: {exc}\n"
                "Please run:  pip install -r requirements.txt"
            )
        except Exception as exc:
            logging.getLogger().error(f"Unexpected error: {exc}", exc_info=True)
        finally:
            self.after(0, self._on_done)

    def _on_done(self) -> None:
        self.progress.stop()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        handler = TextHandler(self.log_box)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        )
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
