import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
import time
import os
import re
import ctypes
import ctypes.wintypes
import subprocess
import requests
import xml.etree.ElementTree as ET
from threading import Thread
from datetime import datetime

# Windows hook constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN     = 0x0100
VK_1           = 0x31  # '1'    key virtual code

# Low level keyboard hook structure
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      ctypes.wintypes.DWORD),
        ("scanCode",    ctypes.wintypes.DWORD),
        ("flags",       ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

# ----------------------------
# Color palette
# ----------------------------
BG          = "#0D1117"
CARD        = "#161B22"
CARD2       = "#1C2333"
BORDER      = "#30363D"
ACCENT      = "#58A6FF"
ACCENT_DIM  = "#1F3A5F"
DANGER      = "#F85149"
DANGER_H    = "#C0392B"
DANGER_DIM  = "#3D1C1C"
SUCCESS     = "#3FB950"
SUCCESS_DIM = "#1A3A2A"
WARNING     = "#D29922"
TEXT_PRI    = "#E6EDF3"
TEXT_SEC    = "#8B949E"
TEXT_HINT   = "#484F58"
GLOW_BLUE   = "#1F6FEB"
GLOW_GREEN  = "#238636"

USERS_FILE   = "users.txt"
CRED_FILE    = "credential.txt"
DOMAIN       = "corp.JABIL.ORG"
SERVER_PATH  = r"C:\temp"  # default, overridden by credential.txt
SOAP_URL     = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx"


class LockApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure Access System")
        self.root.configure(bg=BG)
        self.root.geometry("1000x650")
        self.root.minsize(800, 550)
        self.root.resizable(True, True)

        self.is_locked     = False
        self.is_logged_in  = False
        self._msg_after    = None
        self.server_path   = SERVER_PATH

        # Inactivity timer
        self._inactive_after  = None
        self._countdown_popup = None
        self._countdown_after = None

        self._build_fonts()
        self._build_ui()
        self._update_clock()
        self._load_credentials_and_connect()

        #self.root.bind("1", lambda e: self._on_enter_pressed())

        # Low level keyboard hook — works even when BlockInput is active
        self._hook_thread = Thread(target=self._start_keyboard_hook, daemon=True)
        self._hook_thread.start()

        # Poll system-wide idle time every second
        self._poll_system_idle()

        self._start_auto_scan()

        self._last_processed_log = None  # To track processed log entries and avoid duplicates

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------
    def _build_fonts(self):
        self.font_clock    = ("Consolas", 56, "bold")
        self.font_date     = ("Consolas", 13)
        self.font_title    = ("Segoe UI", 11, "bold")
        self.font_sub      = ("Segoe UI", 9)
        self.font_body     = ("Segoe UI", 10)
        self.font_btn_lg   = ("Segoe UI", 13, "bold")
        self.font_btn_sm   = ("Segoe UI", 9, "bold")
        self.font_badge    = ("Consolas", 8, "bold")
        self.font_status   = ("Segoe UI", 9)
        self.font_hint     = ("Segoe UI", 9)

    # --------------------------------------------------------
    # Main UI
    # --------------------------------------------------------
    def _build_ui(self):
        # ── Top header bar ───────────────────────────────────
        header = tk.Frame(self.root, bg=CARD, height=56)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        left_hdr = tk.Frame(header, bg=CARD)
        left_hdr.pack(side="left", padx=20, pady=12)

        tk.Label(left_hdr, text="●", font=("Segoe UI", 14),
                 bg=CARD, fg=ACCENT).pack(side="left", padx=(0, 8))
        tk.Label(left_hdr, text="SECURE ACCESS SYSTEM",
                 font=self.font_title, bg=CARD,
                 fg=TEXT_PRI).pack(side="left")
        tk.Label(left_hdr, text="  Face Recognition Gateway",
                 font=self.font_sub, bg=CARD,
                 fg=TEXT_HINT).pack(side="left")

        right_hdr = tk.Frame(header, bg=CARD)
        right_hdr.pack(side="right", padx=20)

        self.status_pill = tk.Frame(right_hdr, bg=SUCCESS_DIM, padx=12, pady=4)
        self.status_pill.pack(side="left", padx=(0, 14))

        self.status_dot = tk.Label(self.status_pill, text="●",
                                   font=("Segoe UI", 9),
                                   bg=SUCCESS_DIM, fg=SUCCESS)
        self.status_dot.pack(side="left", padx=(0, 5))

        self.status_var = tk.StringVar(value="UNLOCKED")
        self.status_text_lbl = tk.Label(
            self.status_pill, textvariable=self.status_var,
            font=self.font_badge, bg=SUCCESS_DIM, fg=SUCCESS)
        self.status_text_lbl.pack(side="left")

        self.add_user_btn = self._btn(
            right_hdr, "+ Add User", CARD2, BORDER,
            self._add_user, small=True, outline=True
        )
        self.add_user_btn.pack(side="left")

        self.settings_btn = self._btn(
            right_hdr, "⚙ Settings", CARD2, BORDER,
            self._open_settings, small=True, outline=True
        )
        self.settings_btn.pack(side="left", padx=(8, 0))

        # Accent line under header
        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x")

        # ── Body: left + right ───────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(40, 20), pady=40)
        self._build_left_panel(left)

        right = tk.Frame(body, bg=CARD,
                         highlightthickness=1,
                         highlightbackground=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 30), pady=30)
        self._build_right_panel(right)

        # ── Footer ───────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", side="bottom")

        footer = tk.Frame(self.root, bg=CARD, height=36)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        tk.Label(footer,
                 text="© Secure Access System  |  Powered by Face Recognition AI",
                 font=("Segoe UI", 8), bg=CARD,
                 fg=TEXT_HINT).pack(side="left", padx=20, pady=10)

        self.lock_indicator = tk.Label(
            footer, text="🔓  Input Unlocked",
            font=("Segoe UI", 8, "bold"), bg=CARD, fg=SUCCESS)
        self.lock_indicator.pack(side="right", padx=20)

    # --------------------------------------------------------
    # Left panel
    # --------------------------------------------------------
    def _build_left_panel(self, parent):
        # Clock card
        clock_card = tk.Frame(parent, bg=CARD,
                              highlightthickness=1,
                              highlightbackground=BORDER)
        clock_card.pack(fill="x", pady=(0, 20))

        inner = tk.Frame(clock_card, bg=CARD)
        inner.pack(pady=24, padx=30)

        tk.Label(inner, text="CURRENT TIME",
                 font=("Consolas", 8), bg=CARD,
                 fg=TEXT_HINT).pack(anchor="w")

        self.clock_lbl = tk.Label(inner, text="00:00:00",
                                  font=self.font_clock,
                                  bg=CARD, fg=TEXT_PRI)
        self.clock_lbl.pack(anchor="w")

        self.date_lbl = tk.Label(inner, text="",
                                 font=self.font_date,
                                 bg=CARD, fg=TEXT_SEC)
        self.date_lbl.pack(anchor="w", pady=(2, 0))

        # Divider
        div_row = tk.Frame(parent, bg=BG)
        div_row.pack(fill="x", pady=(0, 20))
        tk.Frame(div_row, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True)
        tk.Label(div_row, text="  ACCESS CONTROL  ",
                 font=("Consolas", 8), bg=BG,
                 fg=TEXT_HINT).pack(side="left")
        tk.Frame(div_row, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True)

        # Login card
        login_card = tk.Frame(parent, bg=CARD,
                              highlightthickness=1,
                              highlightbackground=BORDER)
        login_card.pack(fill="x")

        login_inner = tk.Frame(login_card, bg=CARD)
        login_inner.pack(pady=24, padx=30)

        tk.Label(login_inner, text="AUTHENTICATION REQUIRED",
                 font=("Consolas", 8), bg=CARD,
                 fg=TEXT_HINT).pack(anchor="w", pady=(0, 14))

        self.login_btn = self._btn(
            login_inner, "  🔓   LOGIN  ",
            SUCCESS, GLOW_GREEN,
            self._on_login_click, large=True
        )
        self.login_btn.pack(fill="x")

        self.hint_lbl = tk.Label(
            login_inner,
            text="Press  1  or click to authenticate",
            font=self.font_hint, bg=CARD, fg=TEXT_HINT)
        self.hint_lbl.pack(pady=(10, 0))

        self.msg_var = tk.StringVar(value="")
        self.msg_lbl = tk.Label(
            login_inner, textvariable=self.msg_var,
            font=("Segoe UI", 9, "bold"), bg=CARD,
            fg=TEXT_SEC, wraplength=380, justify="left")
        self.msg_lbl.pack(pady=(12, 0), anchor="w")

    # --------------------------------------------------------
    # Right panel
    # --------------------------------------------------------
    def _build_right_panel(self, parent):
        top = tk.Frame(parent, bg=CARD)
        top.pack(fill="x", padx=16, pady=(16, 0))

        tk.Label(top, text="REGISTERED USERS",
                 font=("Consolas", 9, "bold"),
                 bg=CARD, fg=TEXT_SEC).pack(side="left")

        self.user_count_lbl = tk.Label(top, text="0 users",
                                       font=("Consolas", 8),
                                       bg=CARD, fg=TEXT_HINT)
        self.user_count_lbl.pack(side="right")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(10, 0))

        # User list
        self.users_inner = tk.Frame(parent, bg=CARD)
        self.users_inner.pack(fill="both", expand=True, padx=16, pady=10)

        self._refresh_users()

        # Info box at bottom
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=16)

        info = tk.Frame(parent, bg=CARD2)
        info.pack(fill="x", padx=16, pady=12)

        rows = [
            ("Server", self.server_path),
            ("Log file", "YYYY-MM-DD.log"),
            ("Time window", "5 minutes"),
        ]
        for i, (label, val) in enumerate(rows):
            r = tk.Frame(info, bg=CARD2)
            r.pack(fill="x", pady=3, padx=10)
            tk.Label(r, text=f"{label}:",
                     font=("Segoe UI", 8, "bold"),
                     bg=CARD2, fg=TEXT_HINT).pack(side="left")
            lbl = tk.Label(r, text=val,
                     font=("Consolas", 8),
                     bg=CARD2, fg=TEXT_SEC)
            lbl.pack(side="left", padx=(6, 0))
            if i == 0:
                self.server_info_lbl = lbl  # keep reference to update later

    # --------------------------------------------------------
    # Refresh user list
    # --------------------------------------------------------
    def _refresh_users(self):
        for w in self.users_inner.winfo_children():
            w.destroy()

        users = self._load_users()
        count = len(users)
        self.user_count_lbl.config(
            text=f"{count} user{'s' if count != 1 else ''}")

        if not users:
            tk.Label(self.users_inner,
                     text="No users registered yet.\nClick '+ Add User' to begin.",
                     font=self.font_hint, bg=CARD,
                     fg=TEXT_HINT, justify="left").pack(anchor="w", pady=10)
            return

        for i, ntid in enumerate(users):
            row_bg = CARD2 if i % 2 == 0 else CARD
            row = tk.Frame(self.users_inner, bg=row_bg, padx=10, pady=7)
            row.pack(fill="x", pady=1)

            avatar = tk.Label(row, text=ntid[0].upper(),
                              font=("Segoe UI", 9, "bold"),
                              bg=ACCENT_DIM, fg=ACCENT,
                              width=2, pady=2)
            avatar.pack(side="left", padx=(0, 10))

            tk.Label(row, text=ntid.upper(),
                     font=("Consolas", 9, "bold"),
                     bg=row_bg, fg=TEXT_PRI).pack(side="left")

            # Delete button on the right
            del_btn = tk.Button(
                row, text="✕",
                font=("Segoe UI", 8, "bold"),
                bg=DANGER_DIM, fg=DANGER,
                activebackground=DANGER,
                activeforeground="white",
                relief="flat", bd=0,
                padx=6, pady=1,
                cursor="hand2",
                command=lambda n=ntid: self._delete_user(n)
            )
            del_btn.pack(side="right", padx=(4, 0))

            tk.Label(row, text="● Authorized",
                     font=("Segoe UI", 8),
                     bg=row_bg, fg=SUCCESS).pack(side="right")

    # --------------------------------------------------------
    # Clock
    # --------------------------------------------------------
    def _update_clock(self):
        now = time.localtime()
        self.clock_lbl.config(text=time.strftime("%H:%M:%S", now))
        self.date_lbl.config(
            text=time.strftime("%A, %d %B %Y", now).upper())
        self.root.after(1000, self._update_clock)

    # --------------------------------------------------------
    # Add User
    # --------------------------------------------------------
    def _add_user(self):
        popup = tk.Toplevel(self.root)
        popup.title("Add User")
        popup.configure(bg=CARD)
        popup.resizable(False, False)
        popup.grab_set()

        popup.geometry("460x260")
        popup.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - 460) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
        popup.geometry(f"460x260+{px}+{py}")

        def _on_close():
            popup.destroy()
            self.root.focus_force()

        popup.protocol("WM_DELETE_WINDOW", _on_close)

        # Blue top bar
        tk.Frame(popup, bg=ACCENT, height=4).pack(fill="x")

        # Title
        title_row = tk.Frame(popup, bg=CARD)
        title_row.pack(fill="x", padx=24, pady=(18, 0))
        tk.Label(title_row, text="＋", font=("Segoe UI", 14),
                 bg=CARD, fg=ACCENT).pack(side="left", padx=(0, 8))
        tk.Label(title_row, text="Add Authorized User",
                 font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=TEXT_PRI).pack(side="left")

        tk.Frame(popup, bg=BORDER, height=1).pack(
            fill="x", padx=24, pady=(12, 16))

        # NTID field
        fields = tk.Frame(popup, bg=CARD)
        fields.pack(fill="x", padx=24)

        ntid_row = tk.Frame(fields, bg=CARD)
        ntid_row.pack(fill="x", pady=6)
        tk.Label(ntid_row, text="NTID",
                 font=("Segoe UI", 9, "bold"),
                 bg=CARD, fg=TEXT_HINT,
                 width=10, anchor="w").pack(side="left")
        wrap = tk.Frame(ntid_row, bg=BORDER)
        wrap.pack(side="left", fill="x", expand=True)
        ntid_entry = tk.Entry(wrap, font=("Consolas", 10),
                              bg=CARD2, fg=TEXT_PRI,
                              relief="flat", bd=0,
                              insertbackground=ACCENT)
        ntid_entry.pack(fill="x", padx=1, pady=1, ipady=6, ipadx=8)
        ntid_entry.focus_set()

        # Status label
        status_var = tk.StringVar(value="")
        status_lbl = tk.Label(fields, textvariable=status_var,
                              font=("Segoe UI", 9, "bold"),
                              bg=CARD, fg=TEXT_SEC,
                              wraplength=380, justify="left")
        status_lbl.pack(anchor="w", pady=(8, 0))

        # Buttons
        tk.Frame(popup, bg=BORDER, height=1).pack(
            fill="x", padx=24, pady=(12, 0))

        btn_row = tk.Frame(popup, bg=CARD)
        btn_row.pack(fill="x", padx=24, pady=12)

        add_btn = tk.Button(btn_row, text="  Validate & Add  ",
                            font=("Segoe UI", 9, "bold"),
                            bg=SUCCESS, fg="white",
                            activebackground=GLOW_GREEN,
                            activeforeground="white",
                            relief="flat", bd=0,
                            padx=16, pady=7,
                            cursor="hand2")
        add_btn.pack(side="right")

        tk.Button(btn_row, text="  Cancel  ",
                  font=("Segoe UI", 9, "bold"),
                  bg=CARD2, fg=TEXT_SEC,
                  activebackground=BORDER,
                  activeforeground=TEXT_PRI,
                  relief="flat", bd=0,
                  padx=16, pady=7,
                  cursor="hand2",
                  command=_on_close).pack(side="right", padx=(0, 8))

        def _validate_and_add():
            ntid = ntid_entry.get().strip()

            if not ntid:
                status_var.set("⚠  Please enter an NTID.")
                status_lbl.config(fg=WARNING)
                return

            # Check already registered
            existing = self._load_users()
            if ntid.lower() in existing:
                status_var.set(f"⚠  '{ntid.upper()}' is already registered.")
                status_lbl.config(fg=WARNING)
                return

            # Disable button while validating
            add_btn.config(state="disabled")
            status_var.set("⟳  Checking NTID in AD...")
            status_lbl.config(fg=TEXT_SEC)
            popup.update()

            def _do_validate():
                exists = self._validate_ntid_in_ad(ntid)

                def _done():
                    add_btn.config(state="normal")
                    if exists:
                        with open(USERS_FILE, "a") as f:
                            f.write(ntid.lower() + "\n")
                        self._refresh_users()
                        self._set_msg(
                            f"✓  User '{ntid.upper()}' registered.", SUCCESS)
                        _on_close()
                    else:
                        status_var.set(
                            f"✗  '{ntid.upper()}' does not exist in AD or server unreachable.")
                        status_lbl.config(fg=DANGER)

                popup.after(0, _done)

            Thread(target=_do_validate, daemon=True).start()

        add_btn.config(command=_validate_and_add)
        # Allow Enter key inside popup to trigger validate
        popup.bind("<Return>", lambda e: _validate_and_add())

    # --------------------------------------------------------
    # AD Validation — check NTID exists in AD
    # --------------------------------------------------------
    def _validate_ntid_in_ad(self, ntid: str) -> bool:
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                         xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                         xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <IsUserExistsInAD xmlns="http://jpetewebapp/jtesw_ws/">
              <userName>{ntid}</userName>
            </IsUserExistsInAD>
          </soap12:Body>
        </soap12:Envelope>"""
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": "http://jpetewebapp/jtesw_ws/IsUserExistsInAD"
        }
        try:
            response = requests.post(
                SOAP_URL,
                data=soap.encode("utf-8"),
                headers=headers,
                timeout=15
            )
            response.raise_for_status()
            return self._parse_ad_response(response.text)
        except requests.exceptions.Timeout:
            return False
        except requests.exceptions.RequestException:
            return False
        except Exception:
            return False

    def _parse_ad_response(self, response: str) -> bool:
        if not response or not response.strip():
            return False
        try:
            root = ET.fromstring(response)
            # ReturnedValue is the correct node containing true/false
            for elem in root.iter():
                if "ReturnedValue" in elem.tag:
                    return elem.text.strip().lower() == "true"
            return False
        except ET.ParseError:
            return False
        except Exception:
            return False

    # --------------------------------------------------------
    # Delete User
    # --------------------------------------------------------
    def _delete_user(self, ntid):
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Remove '{ntid.upper()}' from the authorized list?\n\nThis cannot be undone.",
            parent=self.root
        )
        if not confirm:
            return

        users = self._load_users()
        updated = [u for u in users if u != ntid.lower()]

        with open(USERS_FILE, "w") as f:
            for u in updated:
                f.write(u + "\n")

        self._refresh_users()
        self._set_msg(f"✗  User '{ntid.upper()}' removed.", DANGER)

    # --------------------------------------------------------
    # Login / Logout
    # --------------------------------------------------------
    def _on_enter_pressed(self):
        if not self.is_logged_in:
            self._do_login()

    def _on_login_click(self):
        if self.is_logged_in:
            self._do_logout()
        else:
            self._do_login()

    def _do_login(self):
        self._set_msg("⟳  Checking server log...", TEXT_SEC)
        self.root.after(300, self._validate_login)

    def _validate_login(self):
        today   = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(self.server_path, f"{today}.log")
        allowed  = self._load_users()

        # ── 1. Check server is reachable ────────────────────
        if not os.path.exists(self.server_path):
            self._show_error(
                "Server Unreachable",
                "Cannot connect to the server.\n\n"
                f"Path:  {self.server_path}\n\n"
                "Please check your network connection."
            )
            self._set_msg("✗  Server unreachable.", DANGER)
            self._finish_login_check()
            return

        # ── 2. Check today's log file exists ────────────────
        if not os.path.exists(log_file):
            self._show_error(
                "Log File Not Found",
                f"No recognition log found for today.\n\n"
                f"Expected file:  {today}.log\n"
                f"Server path:    {self.server_path}\n\n"
                "Please scan your face at the Pi camera first."
            )
            self._set_msg("✗  No log file for today.", DANGER)
            self._finish_login_check()
            return

        # ── 3. Read the last line────
        status, ntid, detected_time, confidence = self._read_log_match(log_file, allowed)
        line_key = f"{ntid}_{detected_time}"

        if hasattr(self, "_last_processed_log") and self._last_processed_log == line_key:
            #self._last_processed_log = line_key
            return

        self._last_processed_log = line_key

        if status == "no_user":
            self._show_error(
                "No Authorized User Found",
                f"No registered user was found in today's log.\n\n"
                f"File:  {log_file}\n\n"
                "Either scan your face at the Pi camera,\n"
                "or ask admin to register your NTID."
            )
            self._set_msg("✗  No authorized user in today's log.", DANGER)
            self._finish_login_check()
            return

        elif status == "expired":
            self._show_error(
                "Scan Expired",
                f"User '{ntid.upper()}' was detected, but the scan is too old.\n\n"
                f"Detected at: {detected_time.strftime('%H:%M:%S')}\n"
                f"Allowed window: 2 minutes\n\n"
                "Please scan your face again at the camera."
            )
            self._set_msg("⚠  Scan expired. Please re-scan.", WARNING)
            return

        elif status == "valid":
            self._set_msg(
                f"✓  Welcome, {ntid.upper()}!  (Confidence: {confidence}%)",
                SUCCESS
            )
            self._grant_access(name=ntid.upper())
            self._finish_login_check()
            return

    # --------------------------------------------------------
    # Read whole log file, return latest matching registered user
    # --------------------------------------------------------
    def _read_log_match(self, log_file, allowed):
        """
        Returns:
            ("valid", ntid, dt, conf)
            ("expired", ntid, dt, conf)
            ("no_user", None, None, None)
        """

        pattern = re.compile(
            r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]"
            r"\s+Recognized:\s+(\w+)"
            r"\s+\|\s+Confidence:\s+([\d.]+)%"
        )

        try:
            with open(log_file, "r") as f:
                lines = f.readlines()

            now = datetime.now()

            for line in reversed(lines):
                m = pattern.search(line)
                if not m:
                    continue

                ntid = m.group(2).lower()
                log_time = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                conf = m.group(3)

                # Only care about allowed users
                if ntid not in allowed:
                    continue

                diff = (now - log_time).total_seconds()

                if diff <= 120:
                    return ("valid", ntid, log_time, conf)
                else:
                    return ("expired", ntid, log_time, conf)

        except Exception:
            return ("no_user", None, None, None)

        return ("no_user", None, None, None)

    # --------------------------------------------------------
    # Error popup
    # --------------------------------------------------------
    def _show_error(self, title, message):
        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.configure(bg=CARD)
        popup.resizable(False, False)
        popup.grab_set()

        # Center popup
        popup.geometry("480x300")
        popup.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width() - 480) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        popup.geometry(f"480x300+{px}+{py}")

        def _on_close():
            popup.destroy()
            self.root.focus_force()  # Return focus to main window

        popup.protocol("WM_DELETE_WINDOW", _on_close)

        # Red top bar
        tk.Frame(popup, bg=DANGER, height=4).pack(fill="x")

        # Icon + title row
        title_row = tk.Frame(popup, bg=CARD)
        title_row.pack(fill="x", padx=24, pady=(18, 0))

        tk.Label(title_row, text="✕", font=("Segoe UI", 16, "bold"),
                 bg=DANGER_DIM, fg=DANGER,
                 padx=8, pady=2).pack(side="left")

        tk.Label(title_row, text=f"  {title}",
                 font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=TEXT_PRI).pack(side="left")

        # Divider
        tk.Frame(popup, bg=BORDER, height=1).pack(
            fill="x", padx=24, pady=(12, 0))

        # Message body
        tk.Label(popup, text=message,
                 font=("Consolas", 9),
                 bg=CARD, fg=TEXT_SEC,
                 justify="left",
                 wraplength=420).pack(
            anchor="w", padx=24, pady=14)

        # Close button
        close_btn = tk.Button(
            popup, text="  Close  ",
            font=("Segoe UI", 9, "bold"),
            bg=DANGER, fg="white",
            activebackground=DANGER_H,
            activeforeground="white",
            relief="flat", bd=0,
            padx=16, pady=7,
            cursor="hand2",
            command=_on_close
        )
        close_btn.pack(side="right", padx=24, pady=(0, 18))

    # --------------------------------------------------------
    # Credentials — load, save, connect
    # --------------------------------------------------------
    def _load_credentials_and_connect(self):
        creds = self._read_credentials()
        if not creds:
            self._set_msg(
                "⚠  No credentials found. Click ⚙ Settings to configure.", WARNING)
            return

        self.server_path = creds.get("server", SERVER_PATH)
        self._update_server_info_label()

        ntid     = creds.get("ntid", "")
        password = creds.get("password", "")

        if ntid and password:
            Thread(target=self._connect_server,
                   args=(ntid, password), daemon=True).start()

    def _connect_server(self, ntid, password):
        try:
            # Step 1 — Disconnect any existing connection first
            subprocess.run([
                "net", "use",
                self.server_path,
                "/delete", "/yes"
            ], capture_output=True, text=True)

            # Step 2 — Reconnect with credentials
            result = subprocess.run([
                "net", "use",
                self.server_path,
                f"/user:{DOMAIN}\\{ntid}",
                password,
                "/persistent:yes"
            ], capture_output=True, text=True)

            if result.returncode == 0:
                self.root.after(0, lambda: self._set_msg(
                    "✓  Server connected successfully.", SUCCESS))
            else:
                err = result.stderr.strip() or result.stdout.strip()
                self.root.after(0, lambda: self._set_msg(
                    f"⚠  Server connection failed: {err}", WARNING))
        except Exception as e:
            self.root.after(0, lambda: self._set_msg(
                f"⚠  Connection error: {e}", WARNING))

    def _read_credentials(self):
        if not os.path.exists(CRED_FILE):
            return {}
        creds = {}
        with open(CRED_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, val = line.split("=", 1)
                    creds[key.strip()] = val.strip()
        return creds

    def _save_credentials(self, ntid, password, server):
        with open(CRED_FILE, "w") as f:
            f.write(f"ntid={ntid}\n")
            f.write(f"password={password}\n")
            f.write(f"server={server}\n")

    def _update_server_info_label(self):
        # Update the info box in right panel if label exists
        try:
            self.server_info_lbl.config(text=self.server_path)
        except:
            pass

    # --------------------------------------------------------
    # Settings popup
    # --------------------------------------------------------
    def _open_settings(self):
        creds = self._read_credentials()

        popup = tk.Toplevel(self.root)
        popup.title("Settings — Server Credentials")
        popup.configure(bg=CARD)
        popup.resizable(False, False)
        popup.grab_set()

        # Center popup
        popup.geometry("500x370")
        popup.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - 500) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 370) // 2
        popup.geometry(f"500x370+{px}+{py}")

        def _on_close():
            popup.destroy()
            self.root.focus_force()

        popup.protocol("WM_DELETE_WINDOW", _on_close)

        # Blue top bar
        tk.Frame(popup, bg=ACCENT, height=4).pack(fill="x")

        # Title
        title_row = tk.Frame(popup, bg=CARD)
        title_row.pack(fill="x", padx=24, pady=(18, 0))
        tk.Label(title_row, text="⚙", font=("Segoe UI", 14),
                 bg=CARD, fg=ACCENT).pack(side="left", padx=(0, 8))
        tk.Label(title_row, text="Server Credentials",
                 font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=TEXT_PRI).pack(side="left")

        tk.Frame(popup, bg=BORDER, height=1).pack(
            fill="x", padx=24, pady=(12, 16))

        # Fields
        fields = tk.Frame(popup, bg=CARD)
        fields.pack(fill="x", padx=24)

        def _field(parent, label, default="", show=""):
            row = tk.Frame(parent, bg=CARD)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=label,
                     font=("Segoe UI", 9, "bold"),
                     bg=CARD, fg=TEXT_HINT,
                     width=12, anchor="w").pack(side="left")
            wrap = tk.Frame(row, bg=BORDER)
            wrap.pack(side="left", fill="x", expand=True)
            entry = tk.Entry(wrap, font=("Consolas", 10),
                             bg=CARD2, fg=TEXT_PRI,
                             relief="flat", bd=0,
                             insertbackground=ACCENT,
                             show=show)
            entry.pack(fill="x", padx=1, pady=1, ipady=6, ipadx=8)
            entry.insert(0, default)
            return entry

        ntid_entry  = _field(fields, "NTID",
                             creds.get("ntid", ""))
        pass_entry  = _field(fields, "Password",
                             creds.get("password", ""))

        # Server path row with Browse button
        srv_row = tk.Frame(fields, bg=CARD)
        srv_row.pack(fill="x", pady=6)
        tk.Label(srv_row, text="Server Path",
                 font=("Segoe UI", 9, "bold"),
                 bg=CARD, fg=TEXT_HINT,
                 width=12, anchor="w").pack(side="left")

        srv_wrap = tk.Frame(srv_row, bg=BORDER)
        srv_wrap.pack(side="left", fill="x", expand=True)
        srv_entry = tk.Entry(srv_wrap, font=("Consolas", 10),
                             bg=CARD2, fg=TEXT_PRI,
                             relief="flat", bd=0,
                             insertbackground=ACCENT)
        srv_entry.pack(fill="x", padx=1, pady=1, ipady=6, ipadx=8)
        srv_entry.insert(0, creds.get("server", self.server_path))

        def _browse():
            folder = filedialog.askdirectory(
                title="Select Server Log Folder",
                parent=popup
            )
            if folder:
                srv_entry.delete(0, tk.END)
                srv_entry.insert(0, folder)

        browse_btn = tk.Button(
            srv_row, text="Browse",
            font=("Segoe UI", 8, "bold"),
            bg=ACCENT, fg="white",
            activebackground=GLOW_BLUE,
            activeforeground="white",
            relief="flat", bd=0,
            padx=10, pady=7,
            cursor="hand2",
            command=_browse
        )
        browse_btn.pack(side="left", padx=(6, 0))

        # Note about domain
        tk.Label(fields,
                 text=f"Domain: {DOMAIN}  (fixed)",
                 font=("Consolas", 8),
                 bg=CARD, fg=TEXT_HINT).pack(anchor="w", pady=(8, 0))

        # Buttons row
        tk.Frame(popup, bg=BORDER, height=1).pack(
            fill="x", padx=24, pady=(16, 0))

        btn_row = tk.Frame(popup, bg=CARD)
        btn_row.pack(fill="x", padx=24, pady=14)

        def _save():
            ntid     = ntid_entry.get().strip()
            password = pass_entry.get().strip()
            server   = srv_entry.get().strip()

            if not ntid or not password or not server:
                messagebox.showerror(
                    "Error", "All fields are required.", parent=popup)
                return

            self._save_credentials(ntid, password, server)
            self.server_path = server
            self._update_server_info_label()

            _on_close()
            self._set_msg("⟳  Credentials saved. Connecting...", TEXT_SEC)
            Thread(target=self._connect_server,
                   args=(ntid, password), daemon=True).start()

        tk.Button(
            btn_row, text="  Save & Connect  ",
            font=("Segoe UI", 9, "bold"),
            bg=SUCCESS, fg="white",
            activebackground=GLOW_GREEN,
            activeforeground="white",
            relief="flat", bd=0,
            padx=16, pady=7,
            cursor="hand2",
            command=_save
        ).pack(side="right")

        tk.Button(
            btn_row, text="  Cancel  ",
            font=("Segoe UI", 9, "bold"),
            bg=CARD2, fg=TEXT_SEC,
            activebackground=BORDER,
            activeforeground=TEXT_PRI,
            relief="flat", bd=0,
            padx=16, pady=7,
            cursor="hand2",
            command=_on_close
        ).pack(side="right", padx=(0, 8))

    # --------------------------------------------------------
    # finish login check, grant access or show errors based on log file
    # --------------------------------------------------------
    def _finish_login_check(self):
        self._set_msg("", TEXT_SEC)


    # --------------------------------------------------------
    # Auto scan for log file updates
    # --------------------------------------------------------
    def _start_auto_scan(self):
        self._auto_scan_loop()
    
    def _auto_scan_loop(self):
        try:
            self._validate_login()   # reuse your existing logic
        except Exception as e:
            print("[AUTO SCAN ERROR]", e)

        # run every 2 seconds (adjust if needed)
        self.root.after(2000, self._auto_scan_loop)
    # --------------------------------------------------------
    # Low level keyboard hook (bypasses BlockInput)
    # --------------------------------------------------------
    def _start_keyboard_hook(self):
        """
        Installs a low-level keyboard hook that listens for
        the Enter key even when BlockInput is active.
        Runs in a background thread with its own message loop.
        """
        HOOKPROC = ctypes.CFUNCTYPE(
            ctypes.c_longlong, ctypes.c_int,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        )

        def hook_callback(nCode, wParam, lParam):
            try:
                if nCode >= 0 and wParam == WM_KEYDOWN:
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if kb.vkCode == VK_1:
                        self.root.after(0, self._on_enter_pressed)
            except Exception:
                pass
            return ctypes.windll.user32.CallNextHookEx(
                None, nCode,
                ctypes.wintypes.WPARAM(wParam),
                ctypes.wintypes.LPARAM(lParam)
            )

        self._hook_proc = HOOKPROC(hook_callback)
        hook = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, None, 0)

        # Message loop to keep hook alive
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

        ctypes.windll.user32.UnhookWindowsHookEx(hook)

    def _block_input(self, block: bool):
        """
        block=True  → lock all keyboard and mouse input (requires admin)
        block=False → unlock everything
        """
        try:
            ctypes.windll.user32.BlockInput(block)
        except Exception as e:
            self._set_msg(f"⚠  BlockInput failed: {e}", WARNING)

    def _grant_access(self, name=""):
        self.is_logged_in = True
        self.is_locked = False
        self._block_input(False)
        self._reset_inactivity_timer()  # Start inactivity countdown

        self.login_btn.config(
            text="  🔒   LOGOUT  ",
            bg=DANGER, activebackground="#C0392B")
        self.login_btn.bind("<Enter>",
            lambda e: self.login_btn.config(bg="#C0392B"))
        self.login_btn.bind("<Leave>",
            lambda e: self.login_btn.config(bg=DANGER))

        self.hint_lbl.config(text="Click LOGOUT to lock the system")
        self._update_status("LOGGED IN", SUCCESS, SUCCESS_DIM)
        self.lock_indicator.config(text="🔓  Input Unlocked", fg=SUCCESS)
        if not name:
            self._set_msg("✓  Access granted. Welcome!", SUCCESS)

    def _do_logout(self):
        self.is_logged_in = False
        self.is_locked = True
        self._block_input(True)
        self._stop_inactivity_timer()  # Stop timer on logout

        self.login_btn.config(
            text="  🔓   LOGIN  ",
            bg=SUCCESS, activebackground=GLOW_GREEN)
        self.login_btn.bind("<Enter>",
            lambda e: self.login_btn.config(bg=GLOW_GREEN))
        self.login_btn.bind("<Leave>",
            lambda e: self.login_btn.config(bg=SUCCESS))

        self.hint_lbl.config(text="Press  1  to authenticate")
        self._update_status("LOCKED", DANGER, DANGER_DIM)
        self.lock_indicator.config(text="🔒  Input Locked", fg=DANGER)
        self._set_msg("⚠  System locked. Scan face then press 1.", WARNING)
        self.root.focus_force()

    # --------------------------------------------------------
    # System-wide idle detection (GetLastInputInfo)
    # --------------------------------------------------------
    INACTIVE_TOTAL_SECS   = 5 * 60   # 5 minutes total
    INACTIVE_WARNING_SECS = 4 * 60   # show warning at 4 min mark
    COUNTDOWN_SECS        = 60       # 1 minute countdown

    def _get_idle_secs(self):
        """Returns how many seconds the whole PC has been idle."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        elapsed = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return elapsed / 1000.0  # convert ms to seconds

    def _poll_system_idle(self):
        """Poll every second — check system idle time."""
        if self.is_logged_in:
            idle_secs = self._get_idle_secs()

            # Show countdown warning
            if idle_secs >= self.INACTIVE_WARNING_SECS:
                if not self._countdown_popup or \
                   not self._countdown_popup.winfo_exists():
                    self._show_countdown_popup()

            # Auto logout when total time exceeded
            if idle_secs >= self.INACTIVE_TOTAL_SECS:
                self._close_countdown_popup()
                self._do_logout()

        self.root.after(1000, self._poll_system_idle)

    def _reset_inactivity_timer(self):
        # No longer needed — system idle resets automatically
        # when user interacts with ANY app on the PC
        pass

    def _stop_inactivity_timer(self):
        self._close_countdown_popup()

    def _show_countdown_popup(self):
        if not self.is_logged_in:
            return
        if self._countdown_popup and self._countdown_popup.winfo_exists():
            return

        self._countdown_secs_left = self.COUNTDOWN_SECS

        popup = tk.Toplevel(self.root)
        popup.title("Session Expiring")
        popup.configure(bg=CARD)
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        self._countdown_popup = popup

        popup.geometry("360x220")
        popup.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - 360) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 220) // 2
        popup.geometry(f"360x220+{px}+{py}")

        # Orange top bar
        tk.Frame(popup, bg=WARNING, height=4).pack(fill="x")

        tk.Label(popup, text="⚠  Session Expiring",
                 font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=WARNING).pack(pady=(18, 4))

        tk.Label(popup,
                 text="You will be logged out in:",
                 font=("Segoe UI", 9),
                 bg=CARD, fg=TEXT_SEC).pack()

        # Countdown number
        self._cd_var = tk.StringVar(value="60")
        tk.Label(popup, textvariable=self._cd_var,
                 font=("Consolas", 36, "bold"),
                 bg=CARD, fg=DANGER).pack(pady=(8, 4))

        tk.Label(popup, text="seconds",
                 font=("Segoe UI", 9),
                 bg=CARD, fg=TEXT_HINT).pack()

        # Buttons
        btn_row = tk.Frame(popup, bg=CARD)
        btn_row.pack(pady=(12, 0))

        def _stay():
            self._close_countdown_popup()

        tk.Button(btn_row, text="  Stay Logged In  ",
                  font=("Segoe UI", 9, "bold"),
                  bg=SUCCESS, fg="white",
                  activebackground=GLOW_GREEN,
                  activeforeground="white",
                  relief="flat", bd=0,
                  padx=14, pady=7,
                  cursor="hand2",
                  command=_stay).pack(side="left", padx=(0, 8))

        tk.Button(btn_row, text="  Logout Now  ",
                  font=("Segoe UI", 9, "bold"),
                  bg=DANGER, fg="white",
                  activebackground=DANGER_H,
                  activeforeground="white",
                  relief="flat", bd=0,
                  padx=14, pady=7,
                  cursor="hand2",
                  command=lambda: (
                      self._close_countdown_popup(),
                      self._do_logout()
                  )).pack(side="left")

        # Prevent closing via X button — must choose
        popup.protocol("WM_DELETE_WINDOW", _stay)

        # Start ticking
        self._tick_countdown()

    def _tick_countdown(self):
        if not self._countdown_popup or not self._countdown_popup.winfo_exists():
            return
        self._cd_var.set(str(self._countdown_secs_left))

        if self._countdown_secs_left <= 0:
            self._close_countdown_popup()
            self._do_logout()
            return

        self._countdown_secs_left -= 1
        self._countdown_after = self.root.after(1000, self._tick_countdown)

    def _close_countdown_popup(self):
        if self._countdown_after:
            self.root.after_cancel(self._countdown_after)
            self._countdown_after = None
        if self._countdown_popup and self._countdown_popup.winfo_exists():
            self._countdown_popup.destroy()
        self._countdown_popup = None

    def _update_status(self, text, fg, bg):
        self.status_var.set(text)
        self.status_dot.config(fg=fg, bg=bg)
        self.status_pill.config(bg=bg)
        self.status_dot.config(bg=bg)
        self.status_text_lbl.config(bg=bg, fg=fg)

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    def _load_users(self):
        if not os.path.exists(USERS_FILE):
            return []
        with open(USERS_FILE, "r") as f:
            return [l.strip().lower() for l in f if l.strip()]

    def _set_msg(self, text, color=TEXT_SEC):
        self.msg_var.set(text)
        self.msg_lbl.config(fg=color)

    def _btn(self, parent, text, color, hover_color,
             command, small=False, large=False,
             outline=False, state="normal"):
        if large:
            padx, pady, font = 20, 14, self.font_btn_lg
        elif small:
            padx, pady, font = 12, 6, self.font_btn_sm
        else:
            padx, pady, font = 16, 8, self.font_body

        kwargs = dict(
            text=text, font=font,
            bg=color, fg=TEXT_SEC if outline else "white",
            activebackground=hover_color,
            activeforeground=TEXT_PRI if outline else "white",
            relief="flat", bd=0,
            padx=padx, pady=pady,
            cursor="hand2", state=state,
            command=command
        )
        if outline:
            kwargs["highlightthickness"] = 1
            kwargs["highlightbackground"] = BORDER

        btn = tk.Button(parent, **kwargs)
        btn.bind("<Enter>", lambda e, b=btn, c=hover_color:
                 b.config(bg=c) if str(b["state"]) != "disabled" else None)
        btn.bind("<Leave>", lambda e, b=btn, c=color:
                 b.config(bg=c) if str(b["state"]) != "disabled" else None)
        return btn


# --------------------------------------------------------
# Entry point
# --------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = LockApp(root)
    # Safety: always unblock input when app closes
    root.protocol("WM_DELETE_WINDOW", lambda: (
        app._block_input(False), root.destroy()))
    root.mainloop()