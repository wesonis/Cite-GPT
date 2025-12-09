from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, List
import os
import webbrowser

try:
    from .controller import AssistantController
except ImportError:  # pragma: no cover - fallback for direct execution
    from controller import AssistantController  # type: ignore


class AssistantGUI:
    def __init__(self, controller: AssistantController) -> None:
        self._controller = controller
        self._controller.add_status_listener(self._handle_status)
        self._controller.add_log_listener(self._append_log)
        self._controller.add_transcript_listener(self._handle_transcript)
        self._controller.add_recording_listener(self._handle_recording_state)
        self._controller.add_results_listener(self._handle_results)
        self._controller.set_retry_prompt_handler(self._prompt_retry)

        self._root = tk.Tk()
        self._root.title("Zotero Voice Assistant")
        self._root.geometry("520x750")

        self._status_var = tk.StringVar(value="Inactive")
        self._transcript_var = tk.StringVar(value="Waiting for audio...")
        self._recording_state = tk.BooleanVar(value=False)
        self._results: List[dict] = []
        self._session_active = False

        header = ttk.Label(
            self._root,
            text="Cite-GPT",
            font=("Segoe UI", 16, "bold"),
        )
        header.pack(pady=(16, 8))

        self._record_button = ttk.Button(
            self._root,
            text="Ask Cite-GPT",
            command=self._handle_record_button,
            width=18,
        )
        self._record_button.pack(pady=(0, 4))

        status = ttk.Label(self._root, textvariable=self._status_var)
        status.pack(pady=(8, 4))

        record_frame = ttk.LabelFrame(self._root, text="Recording state")
        record_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._recording_badge = RecordingBadge(record_frame)
        self._recording_badge.pack(fill=tk.X, padx=8, pady=8)

        transcript_frame = ttk.LabelFrame(self._root, text="Last transcript")
        transcript_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        transcript_label = ttk.Label(
            transcript_frame,
            textvariable=self._transcript_var,
            wraplength=460,
            justify=tk.LEFT,
        )
        transcript_label.pack(fill=tk.X, padx=8, pady=8)

        results_frame = ttk.LabelFrame(self._root, text="Latest results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        list_container = ttk.Frame(results_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._results_list = tk.Listbox(list_container, height=8, activestyle="dotbox")
        scrollbar = ttk.Scrollbar(
            list_container, orient=tk.VERTICAL, command=self._results_list.yview
        )
        self._results_list.configure(yscrollcommand=scrollbar.set)
        self._results_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._results_list.bind("<<ListboxSelect>>", lambda _event: self._update_button_state())
        self._results_list.bind("<Double-Button-1>", lambda _event: self._open_selected())
        self._results_list.insert(tk.END, "No results yet")

        button_row = ttk.Frame(results_frame)
        button_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._open_button = ttk.Button(
            button_row, text="Open Selection", command=self._open_selected
        )
        self._open_button.pack(side=tk.LEFT)
        self._clear_button = ttk.Button(button_row, text="Clear", command=self._clear_results)
        self._clear_button.pack(side=tk.LEFT, padx=(8, 0))
        self._open_button.configure(state=tk.DISABLED)
        self._clear_button.configure(state=tk.DISABLED)

        self._log = tk.Text(self._root, height=8, state="disabled")
        self._log.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

    def run(self) -> None:
        self._root.mainloop()

    def _handle_record_button(self) -> None:
        if self._session_active:
            self._record_button.configure(text="Stopping...")
            self._controller.stop()
        else:
            self._record_button.configure(text="Stop Recording")
            self._session_active = True
            self._controller.start()

    def _handle_status(self, active: bool) -> None:
        def update() -> None:
            self._status_var.set("Active" if active else "Inactive")
            self._session_active = active
            self._record_button.configure(text="Stop Recording" if active else "Ask Cite-GPT")
            if not active:
                self._recording_badge.set_state(False)

        self._schedule(update)

    def _append_log(self, message: str) -> None:
        def update() -> None:
            self._log.configure(state="normal")
            self._log.insert(tk.END, f"{message}\n")
            self._log.configure(state="disabled")
            self._log.see(tk.END)

        self._schedule(update)

    def _handle_transcript(self, transcript: str) -> None:
        def update() -> None:
            if transcript.strip():
                self._transcript_var.set(transcript.strip())
            else:
                self._transcript_var.set("No speech detected")

        self._schedule(update)

    def _handle_recording_state(self, active: bool) -> None:
        def update() -> None:
            self._recording_state.set(active)
            self._recording_badge.set_state(active)

        self._schedule(update)

    def _handle_results(self, items: List[dict]) -> None:
        def update() -> None:
            self._results = items
            self._results_list.delete(0, tk.END)
            if not items:
                self._results_list.insert(tk.END, "No results yet")
                self._open_button.configure(state=tk.DISABLED)
                self._clear_button.configure(state=tk.DISABLED)
                return
            for item in items:
                self._results_list.insert(tk.END, _format_item_label(item))
            self._results_list.selection_clear(0, tk.END)
            self._results_list.selection_set(0)
            self._update_button_state()

        self._schedule(update)

    def _open_selected(self) -> None:
        selection = self._results_list.curselection()
        if not selection or selection[0] >= len(self._results):
            return
        item = self._results[selection[0]]
        location = self._controller.resolve_item_location(item)
        if not location:
            messagebox.showwarning("Unavailable", "No attachment or URL was found for this item.")
            return
        try:
            # self._root.clipboard_clear()
            # self._root.clipboard_append(location)
            if "http" in location.lower():
                webbrowser.open_new_tab(location)
            elif "pdf" in location.lower():
                os.startfile(location)
            else:
                self._root.clipboard_clear()
                self._root.clipboard_append(location)

        except tk.TclError:
            # self._append_log("Clipboard unavailable on this system; displaying path instead.")
            self._append_log("Unable to open file or find URL - displaying path instead")
            messagebox.showinfo("Item location", location)
        else:
            # self._append_log("PDF path copied to clipboard.")
            # messagebox.showinfo("Copied", "PDF path copied to clipboard.")
            self._append_log("")

    def _clear_results(self) -> None:
        self._results = []
        self._results_list.delete(0, tk.END)
        self._results_list.insert(tk.END, "No results yet")
        self._open_button.configure(state=tk.DISABLED)
        self._clear_button.configure(state=tk.DISABLED)

    def _update_button_state(self) -> None:
        valid = bool(self._results and self._results_list.curselection())
        self._open_button.configure(state=tk.NORMAL if valid else tk.DISABLED)
        self._clear_button.configure(state=tk.NORMAL if self._results else tk.DISABLED)

    def _prompt_retry(self, expand_allowed: bool) -> str:
        response_holder = {"value": "retry"}
        wait_event = threading.Event()

        def prompt() -> None:
            dialog = RetryDialog(self._root, expand_allowed)
            response_holder["value"] = dialog.result or "cancel"
            wait_event.set()

        self._schedule(prompt)
        wait_event.wait()
        return response_holder["value"]

    def _schedule(self, func: Callable[[], None]) -> None:
        if self._root.winfo_exists():
            self._root.after(0, func)


class RecordingBadge(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._canvas = tk.Canvas(self, width=18, height=18, highlightthickness=0)
        self._dot = self._canvas.create_oval(2, 2, 16, 16, outline="", fill="#9ca3af")
        self._canvas.pack(side=tk.LEFT, padx=(0, 8))
        self._label = ttk.Label(self, text="Idle")
        self._label.pack(side=tk.LEFT)

    def set_state(self, active: bool) -> None:
        color = "#ef4444" if active else "#9ca3af"
        text = "Recording" if active else "Idle"
        self._canvas.itemconfig(self._dot, fill=color)
        self._label.configure(text=text)


class RetryDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Misc, expand_allowed: bool) -> None:
        self._expand_allowed = expand_allowed
        super().__init__(parent, title="No Zotero Matches")

    def body(self, master: tk.Misc) -> tk.Widget:
        ttk.Label(
            master,
            text="No items matched that query. What would you like to do?",
            wraplength=320,
            justify=tk.LEFT,
        ).pack(padx=8, pady=8)
        return master

    def buttonbox(self) -> None:
        box = ttk.Frame(self)
        box.pack(padx=8, pady=(0, 8))

        retry_btn = ttk.Button(box, text="Record Again", command=lambda: self._close_with("retry"))
        retry_btn.pack(side=tk.LEFT)

        if self._expand_allowed:
            expand_btn = ttk.Button(
                box, text="Expand Search", command=lambda: self._close_with("expand")
            )
            expand_btn.pack(side=tk.LEFT, padx=(8, 0))

        cancel_btn = ttk.Button(box, text="Cancel", command=lambda: self._close_with("cancel"))
        cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

    def _close_with(self, value: str) -> None:
        self.result = value
        self.ok()


def _format_item_label(item: dict) -> str:
    data = item.get("data", {})
    title = data.get("title", "Untitled")
    author = _format_authors(data)
    year = (data.get("date") or "").split("-")[0]
    return f"{title} — {author} ({year})".strip()


def _format_authors(data: dict) -> str:
    creators = data.get("creators", [])
    if not creators:
        return "Unknown"
    primary = creators[0]
    first = primary.get("firstName", "").strip()
    last = primary.get("lastName", "").strip()
    return " ".join(part for part in (first, last) if part) or "Unknown"
