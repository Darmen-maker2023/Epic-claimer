"""GUI shell for the Epic Games free games claimer (packaged as EpicClaimer.exe)."""
import asyncio
import json
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import customtkinter as ctk

BG = "#0d1117"
PANEL = "#161b22"
PANEL2 = "#1c2333"
ACCENT = "#2f81f7"
ACCENT_HOVER = "#1f6feb"
SUCCESS = "#3fb950"
WARN = "#d29922"
DANGER = "#f85149"
TEXT = "#e6edf3"
MUTED = "#8b949e"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Tee:
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        if not s:
            return
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        pass

    def reconfigure(self, **kwargs):
        pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Epic Free Games Claimer")
        self.geometry("900x700")
        self.minsize(780, 600)
        self.configure(fg_color=BG)

        import claimer
        self.claimer = claimer

        self.text_q = queue.Queue()
        self.done_q = queue.Queue()
        self.busy = False
        self.daemon_stop = None

        sys.stdout = Tee(_QueueWriter(self.text_q), _FileLog())
        sys.stderr = Tee(_QueueWriter(self.text_q), _FileLog())

        self._build_header()
        self._build_tabs()
        self._build_log()
        self._build_statusbar()
        self._poll()

    # ------------------------------------------------------------------ UI
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14, height=86)
        head.pack(fill="x", padx=16, pady=(16, 8))
        head.pack_propagate(False)

        title = ctk.CTkLabel(head, text="EPIC  FREE  CLAIMER",
                             font=ctk.CTkFont(family="Segoe UI Semibold", size=24),
                             text_color=TEXT)
        title.pack(anchor="w", padx=20, pady=(14, 0))
        sub = ctk.CTkLabel(
            head,
            text="Автозабор бесплатных игр Epic Games на нескольких аккаунтах",
            font=ctk.CTkFont(size=13), text_color=MUTED)
        sub.pack(anchor="w", padx=20)

        self.conn_dot = ctk.CTkLabel(head, text="● готов", width=80,
                                     font=ctk.CTkFont(size=12), text_color=SUCCESS)
        self.conn_dot.place(relx=1.0, rely=0.5, anchor="e", x=-20)

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, fg_color=PANEL, corner_radius=14,
                                      segmented_button_fg_color=PANEL2,
                                      segmented_button_selected_color=ACCENT)
        self.tabview.pack(fill="x", padx=16, pady=8)
        self.tabview.add("Главная")
        self.tabview.add("Настройки")
        self.tabview.set("Главная")

        main = self.tabview.tab("Главная")
        self.action_btns = []

        row0 = ctk.CTkFrame(main, fg_color="transparent")
        row0.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(row0, text="Вход в аккаунты (один раз, сессия сохраняется):",
                     font=ctk.CTkFont(size=12), text_color=MUTED).pack(anchor="w")

        self.acc_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.acc_frame.pack(fill="x", padx=4, pady=4)
        self._build_account_buttons()

        row1 = ctk.CTkFrame(main, fg_color="transparent")
        row1.pack(fill="x", padx=4, pady=(10, 4))

        self.claim_btn = ctk.CTkButton(
            row1, text="▶  ЗАБРАТЬ ВСЁ СЕЙЧАС", height=52, corner_radius=12,
            font=ctk.CTkFont(family="Segoe UI Semibold", size=16),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: self._run(self._task_claim))
        self.claim_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.action_btns.append(self.claim_btn)

        self.list_btn = ctk.CTkButton(
            row1, text="Список\nраздач", width=110, height=52, corner_radius=12,
            fg_color=PANEL2, hover_color="#253044", text_color=TEXT,
            command=lambda: self._run(self._task_list))
        self.list_btn.pack(side="left", padx=(0, 8))
        self.action_btns.append(self.list_btn)

        self.folder_btn = ctk.CTkButton(
            row1, text="Папка\nпрограммы", width=110, height=52, corner_radius=12,
            fg_color=PANEL2, hover_color="#253044", text_color=TEXT,
            command=self._open_folder)
        self.folder_btn.pack(side="left")
        self.action_btns.append(self.folder_btn)

        row2 = ctk.CTkFrame(main, fg_color="transparent")
        row2.pack(fill="x", padx=4, pady=(10, 10))

        self.daemon_var = ctk.BooleanVar(value=False)
        self.daemon_sw = ctk.CTkSwitch(
            row2, text="Автопроверка по расписанию", variable=self.daemon_var,
            font=ctk.CTkFont(size=13), progress_color=ACCENT,
            button_color=TEXT, button_hover_color="#c9d1d9",
            command=self._toggle_daemon)
        self.daemon_sw.pack(side="left")
        self.action_btns.append(self.daemon_sw)

        self.sync_info = ctk.CTkLabel(
            row2,
            text="Синхронизация Яндекса включается при первом входе",
            font=ctk.CTkFont(size=12), text_color=MUTED)
        self.sync_info.pack(side="right")

        # ---- settings tab
        st = self.tabview.tab("Настройки")
        grid = ctk.CTkFrame(st, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=8, pady=8)
        grid.columnconfigure(1, weight=1)

        cfg = self.claimer.CONFIG

        def field(r, label):
            ctk.CTkLabel(grid, text=label, font=ctk.CTkFont(size=12),
                         text_color=MUTED).grid(row=r, column=0, sticky="w",
                                                padx=(0, 12), pady=6)

        field(0, "Аккаунты (через запятую)")
        self.acc_entry = ctk.CTkEntry(grid, placeholder_text="acc1, acc2, acc3")
        self.acc_entry.insert(0, ", ".join(cfg.get("accounts", [])))
        self.acc_entry.grid(row=0, column=1, sticky="ew", pady=6)

        field(1, "Проверка кажд N часов")
        self.int_entry = ctk.CTkEntry(grid, placeholder_text="6")
        self.int_entry.insert(0, str(cfg.get("check_interval_hours", 6)))
        self.int_entry.grid(row=1, column=1, sticky="ew", pady=6)

        field(2, "Telegram bot token")
        self.tok_entry = ctk.CTkEntry(grid, placeholder_text="123456:ABC-DEF...")
        self.tok_entry.insert(0, cfg.get("telegram_bot_token", ""))
        self.tok_entry.grid(row=2, column=1, sticky="ew", pady=6)

        field(3, "Telegram chat id")
        self.chat_entry = ctk.CTkEntry(grid, placeholder_text="-1001234567890")
        self.chat_entry.insert(0, cfg.get("telegram_chat_id", ""))
        self.chat_entry.grid(row=3, column=1, sticky="ew", pady=6)

        self.bg_var = ctk.BooleanVar(value=bool(cfg.get("headless", False)))
        ctk.CTkCheckBox(grid, text="Фоновый режим (без окон браузера)",
                        variable=self.bg_var, fg_color=ACCENT,
                        font=ctk.CTkFont(size=13)).grid(
            row=4, column=1, sticky="w", pady=6)

        self.sync_var = ctk.BooleanVar(value=bool(cfg.get("sync", True)))
        ctk.CTkCheckBox(grid, text="Синхронизация Яндекса (пароли, закладки)",
                        variable=self.sync_var, fg_color=ACCENT,
                        font=ctk.CTkFont(size=13)).grid(
            row=5, column=1, sticky="w", pady=6)

        self.save_btn = ctk.CTkButton(
            grid, text="Сохранить настройки", width=200, height=40,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._save_config)
        self.save_btn.grid(row=6, column=1, sticky="w", pady=(14, 6))

    def _build_account_buttons(self):
        for w in self.acc_frame.winfo_children():
            w.destroy()
        for acc in self.claimer.CONFIG.get("accounts", []):
            b = ctk.CTkButton(
                self.acc_frame, text=f"Войти · {acc}", width=150, height=36,
                corner_radius=10, fg_color=PANEL2, hover_color="#253044",
                text_color=TEXT,
                command=lambda a=acc: self._run(lambda: self._task_login(a)))
            b.pack(side="left", padx=(0, 8))
            self.action_btns.append(b)

    def _build_log(self):
        frame = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=14)
        frame.pack(fill="both", expand=True, padx=16, pady=8)
        ctk.CTkLabel(frame, text="ЖУРНАЛ", font=ctk.CTkFont(size=11),
                     text_color=MUTED).pack(anchor="w", padx=14, pady=(10, 0))
        self.log = ctk.CTkTextbox(frame, fg_color=BG, text_color=TEXT,
                                  font=ctk.CTkFont(family="Consolas", size=12),
                                  corner_radius=10, border_width=0,
                                  state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent", height=34)
        bar.pack(fill="x", padx=16, pady=(0, 10))
        self.status = ctk.CTkLabel(bar, text="Готово", anchor="w",
                                   font=ctk.CTkFont(size=12), text_color=MUTED)
        self.status.pack(side="left")
        self.progress = ctk.CTkProgressBar(bar, width=220, mode="indeterminate",
                                           progress_color=ACCENT)
        self.progress.pack(side="right")
        self.progress.set(0)

    # ------------------------------------------------------------- helpers
    def _append_log(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        lines = int(self.log.get("1.0", "end").count("\n"))
        if lines > 4000:
            self.log.delete("1.0", f"{lines - 3000}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text, color=MUTED):
        self.status.configure(text=text, text_color=color)
        self.conn_dot.configure(text="● работаю" if color == ACCENT else "● готов",
                                text_color=ACCENT if color == ACCENT else SUCCESS)

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for b in self.action_btns:
            try:
                b.configure(state=state)
            except Exception:
                pass
        if busy:
            self.claim_btn.configure(text="Идёт процесс...")
            self.progress.start()
            self._set_status("Выполняется...", ACCENT)
        else:
            self.claim_btn.configure(text="▶  ЗАБРАТЬ ВСЁ СЕЙЧАС")
            self.progress.stop()
            self.progress.set(0)

    def _run(self, fn):
        if self.busy:
            return
        self.busy = True
        self._set_busy(True)

        def worker():
            try:
                result = fn()
            except Exception:
                result = None
                self.text_q.put(traceback.format_exc())
            self.done_q.put(result)

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, result):
        self.busy = False
        self._set_busy(False)
        if result:
            self._set_status(str(result).splitlines()[-1][:80], SUCCESS)

    def _open_folder(self):
        import os
        os.startfile(self.claimer.ROOT)

    # --------------------------------------------------------------- tasks
    def _task_claim(self):
        summary = asyncio.run(self.claimer.cmd_claim())
        return summary

    def _task_list(self):
        asyncio.run(self.claimer.cmd_list())
        return "Список раздач обновлён"

    def _task_login(self, acc):
        asyncio.run(self.claimer.cmd_login(acc))
        return f"Вход: {acc} — проверено"

    def _save_config(self):
        cfg = self.claimer.load_config()
        accs = [a.strip() for a in self.acc_entry.get().split(",") if a.strip()]
        if accs:
            cfg["accounts"] = accs
        try:
            cfg["check_interval_hours"] = max(1, float(self.int_entry.get()))
        except ValueError:
            pass
        cfg["telegram_bot_token"] = self.tok_entry.get().strip()
        cfg["telegram_chat_id"] = self.chat_entry.get().strip()
        cfg["headless"] = bool(self.bg_var.get())
        cfg["sync"] = bool(self.sync_var.get())
        (self.claimer.ROOT / "config.json").write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        self.claimer.CONFIG = cfg
        self._build_account_buttons()
        self._append_log("[settings] Настройки сохранены\n")
        self._set_status("Настройки сохранены", SUCCESS)

    def _toggle_daemon(self):
        if self.daemon_var.get():
            self.daemon_stop = threading.Event()

            def loop():
                self.text_q.put("[daemon] Автопроверка включена\n")
                while not self.daemon_stop.is_set():
                    try:
                        asyncio.run(self.claimer.cmd_claim())
                    except Exception:
                        self.text_q.put(traceback.format_exc())
                    hours = self.claimer.CONFIG.get("check_interval_hours", 6)
                    self.text_q.put(f"[daemon] Следующая проверка через {hours} ч.\n")
                    self.daemon_stop.wait(hours * 3600)

            threading.Thread(target=loop, daemon=True).start()
        elif self.daemon_stop:
            self.daemon_stop.set()
            self.daemon_stop = None
            self.text_q.put("[daemon] Автопроверка выключена\n")

    # --------------------------------------------------------------- polls
    def _poll(self):
        try:
            while True:
                self._append_log(self.text_q.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._finish(self.done_q.get_nowait())
        except queue.Empty:
            pass
        self.after(80, self._poll)


class _QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class _FileLog:
    _fh = None

    def write(self, s):
        if not s:
            return
        try:
            import claimer
            if self._fh is None:
                self._fh = open(claimer.ROOT / "claim.log", "a",
                                encoding="utf-8", buffering=1)
            self._fh.write(s)
        except Exception:
            pass

    def flush(self):
        pass


def run_cli():
    import claimer
    fh = open(claimer.ROOT / "claim.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(fh)
    sys.stderr = Tee(fh)
    if "--daemon" in sys.argv:
        asyncio.run(claimer.cmd_daemon())
    else:
        asyncio.run(claimer.cmd_claim())


def main():
    if any(a in ("--claim", "--daemon") for a in sys.argv):
        run_cli()
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
