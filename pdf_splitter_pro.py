import os
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD
from PyPDF2 import PdfReader, PdfWriter


APP_TITLE = "PDF Splitter PRO"
DEFAULT_CHUNK = 15


class App:
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} ??")
        self.root.geometry("560x340")

        self.dropped_items = []
        self.ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self.is_running = False

        self._build_ui()
        self.root.after(50, self._poll_ui_queue)

    def _build_ui(self):
        # Drop area
        self.label_drop = tk.Label(
            self.root,
            text="Zieh PDFs oder Ordner hier rein ??",
            relief="groove",
            height=5
        )
        self.label_drop.pack(fill="x", padx=10, pady=10)
        self.label_drop.drop_target_register(DND_FILES)
        self.label_drop.dnd_bind("<<Drop>>", self._on_drop)

        # Output folder
        tk.Label(self.root, text="Output-Ordner:").pack(anchor="w", padx=10)
        frame_out = tk.Frame(self.root)
        frame_out.pack(fill="x", padx=10)

        self.entry_output = tk.Entry(frame_out)
        self.entry_output.pack(side="left", fill="x", expand=True)

        tk.Button(frame_out, text="Browse", command=self._choose_output).pack(side="right")

        # Chunk + threads
        grid = tk.Frame(self.root)
        grid.pack(fill="x", padx=10, pady=8)

        tk.Label(grid, text="Seiten pro Chunk:").grid(row=0, column=0, sticky="w")
        self.entry_chunk = tk.Entry(grid, width=8)
        self.entry_chunk.insert(0, str(DEFAULT_CHUNK))
        self.entry_chunk.grid(row=0, column=1, sticky="w", padx=(6, 20))

        tk.Label(grid, text="Threads (leer = auto):").grid(row=0, column=2, sticky="w")
        self.entry_threads = tk.Entry(grid, width=8)
        self.entry_threads.grid(row=0, column=3, sticky="w", padx=(6, 0))

        grid.grid_columnconfigure(4, weight=1)

        # Progress
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(8, 4))

        self.status_label = tk.Label(self.root, text="Bereit")
        self.status_label.pack(anchor="w", padx=10)

        self.stats_label = tk.Label(self.root, text="0/0 verarbeitet | Fehler: 0")
        self.stats_label.pack(anchor="w", padx=10, pady=(2, 8))

        # Buttons
        btns = tk.Frame(self.root)
        btns.pack(fill="x", padx=10, pady=6)

        self.btn_start = tk.Button(btns, text="Start ??", command=self.start)
        self.btn_start.pack(side="left")

        self.btn_clear = tk.Button(btns, text="Reset", command=self.reset)
        self.btn_clear.pack(side="left", padx=8)

        self.btn_open_log = tk.Button(btns, text="Fehler-Log oeffnen", command=self.open_log, state="disabled")
        self.btn_open_log.pack(side="right")

        self.log_path = None

    def _on_drop(self, event):
        items = self.root.tk.splitlist(event.data)
        cleaned = []
        for item in items:
            item = item.strip()
            if os.path.isdir(item) or item.lower().endswith(".pdf"):
                cleaned.append(item)

        self.dropped_items = cleaned
        self.label_drop.config(text=f"{len(self.dropped_items)} Item(s) geladen ??")

    def _choose_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.entry_output.delete(0, tk.END)
            self.entry_output.insert(0, folder)

    def reset(self):
        if self.is_running:
            messagebox.showwarning("Laeuft", "Gerade wird verarbeitet. Reset geht danach ??")
            return
        self.dropped_items = []
        self.label_drop.config(text="Zieh PDFs oder Ordner hier rein ??")
        self.progress["value"] = 0
        self.progress["maximum"] = 1
        self.status_label.config(text="Bereit")
        self.stats_label.config(text="0/0 verarbeitet | Fehler: 0")
        self.btn_open_log.config(state="disabled")
        self.log_path = None

    def open_log(self):
        if self.log_path and os.path.isfile(self.log_path):
            try:
                os.startfile(self.log_path)  # Windows
            except Exception:
                messagebox.showinfo("Info", f"Log liegt hier:\n{self.log_path}")

    @staticmethod
    def _collect_pdfs(dropped_items):
        """
        Returns list of tuples: (pdf_path, base_input_root)
        base_input_root is used to preserve relative folder structure into output.
        """
        pdfs = []
        for item in dropped_items:
            if os.path.isfile(item) and item.lower().endswith(".pdf"):
                pdfs.append((item, os.path.dirname(item)))
            elif os.path.isdir(item):
                base_root = item
                for root_dir, _, files in os.walk(item):
                    for f in files:
                        if f.lower().endswith(".pdf"):
                            pdfs.append((os.path.join(root_dir, f), base_root))
        return pdfs

    @staticmethod
    def _split_one(pdf_path, base_input_root, output_root, chunk_size):
        """
        Returns: (ok: bool, payload)
        ok True => payload = pdf_path
        ok False => payload = (pdf_path, error_str)
        """
        try:
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)

            # Preserve subfolder structure relative to dropped base root
            rel_dir = os.path.relpath(os.path.dirname(pdf_path), base_input_root)
            out_dir = os.path.join(output_root, rel_dir) if rel_dir != "." else output_root
            os.makedirs(out_dir, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(pdf_path))[0]

            for start in range(0, total_pages, chunk_size):
                writer = PdfWriter()
                end = min(start + chunk_size, total_pages)

                for i in range(start, end):
                    writer.add_page(reader.pages[i])

                out_file = os.path.join(out_dir, f"{base_name}_{start+1}-{end}.pdf")
                with open(out_file, "wb") as f:
                    writer.write(f)

            return True, pdf_path
        except Exception as e:
            return False, (pdf_path, str(e))

    def start(self):
        if self.is_running:
            return

        if not self.dropped_items:
            messagebox.showerror("Fehler", "Nichts gedroppt!")
            return

        output_root = self.entry_output.get().strip()
        if not output_root:
            messagebox.showerror("Fehler", "Bitte Output-Ordner waehlen!")
            return

        try:
            chunk_size = int(self.entry_chunk.get().strip())
            if chunk_size <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Fehler", "Chunk-Groesse muss eine positive Zahl sein!")
            return

        threads_raw = self.entry_threads.get().strip()
        if threads_raw:
            try:
                max_workers = int(threads_raw)
                if max_workers <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("Fehler", "Threads muss leer oder eine positive Zahl sein!")
                return
        else:
            # Threads: auto, but keep it sane for IO/CPU mix
            cpu = os.cpu_count() or 4
            max_workers = min(8, max(2, cpu))

        pdfs = self._collect_pdfs(self.dropped_items)
        total = len(pdfs)
        if total == 0:
            messagebox.showwarning("Hinweis", "Keine PDFs gefunden.")
            return

        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_clear.config(state="disabled")
        self.btn_open_log.config(state="disabled")

        self.progress["maximum"] = total
        self.progress["value"] = 0
        self.status_label.config(text=f"Starte… (Threads: {max_workers})")
        self.stats_label.config(text=f"0/{total} verarbeitet | Fehler: 0")

        self.log_path = os.path.join(output_root, "error_log.txt")

        def bg():
            processed = 0
            errors = 0
            error_lines = []

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(self._split_one, p, base, output_root, chunk_size) for (p, base) in pdfs]

                for fut in as_completed(futures):
                    ok, payload = fut.result()
                    processed += 1

                    if not ok:
                        errors += 1
                        pdf_path, err = payload
                        error_lines.append(f"{pdf_path}\n{err}\n")

                    # UI update request
                    self.ui_queue.put(("progress", processed, total, errors))

            # write log if needed
            if error_lines:
                try:
                    with open(self.log_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(error_lines))
                except Exception:
                    pass

            self.ui_queue.put(("done", total, errors, bool(error_lines)))

        threading.Thread(target=bg, daemon=True).start()

    def _poll_ui_queue(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                kind = msg[0]

                if kind == "progress":
                    _, processed, total, errors = msg
                    self.progress["value"] = processed
                    self.status_label.config(text="Verarbeite…")
                    self.stats_label.config(text=f"{processed}/{total} verarbeitet | Fehler: {errors}")

                elif kind == "done":
                    _, total, errors, has_log = msg
                    self.is_running = False
                    self.btn_start.config(state="normal")
                    self.btn_clear.config(state="normal")
                    self.btn_open_log.config(state="normal" if has_log else "disabled")

                    self.status_label.config(text="Fertig ??")
                    self.stats_label.config(text=f"{total}/{total} verarbeitet | Fehler: {errors}")

                    messagebox.showinfo("Fertig", f"{total} PDFs verarbeitet.\nFehler: {errors}")
        except queue.Empty:
            pass

        self.root.after(50, self._poll_ui_queue)


def main():
    root = TkinterDnD.Tk()
    # ttk styles (minimal)
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
