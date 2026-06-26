#!/usr/bin/env python3
"""
MARE Testbed Cold Start — GUI (Windows + Linux)
Requires: pip install paramiko

Run normally:          python app.py
Terminal helper mode:  python app.py --terminal <host> <user> <password> <session>
                       (opened automatically by the GUI for each service)
"""
import sys
import os
import threading
import time

try:
    import paramiko
except ImportError:
    print("Install paramiko first:  python -m pip install paramiko")
    raise SystemExit(1)

# ──────────────────────────────────────────────────────────────────────────────
# Terminal helper mode  (invoked by the GUI via  cmd /k python app.py --terminal ...)
# ──────────────────────────────────────────────────────────────────────────────

SPECIAL_KEYS = {
    b'H': b'\x1b[A',  b'P': b'\x1b[B',  b'M': b'\x1b[C',  b'K': b'\x1b[D',
    b'I': b'\x1b[5~', b'Q': b'\x1b[6~', b'G': b'\x1b[H',  b'O': b'\x1b[F',
    b'S': b'\x1b[3~', b';': b'\x1bOP',  b'<': b'\x1bOQ',  b'=': b'\x1bOR',
    b'>': b'\x1bOS',
}

def _run_terminal(host, user, password, session):
    """Interactive SSH terminal that attaches to a remote tmux session."""
    # Enable ANSI / VT processing on Windows
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        ENABLE_VT = 0x0004
        for hid in (-10, -11):
            h = k32.GetStdHandle(hid)
            m = ctypes.c_ulong()
            k32.GetConsoleMode(h, ctypes.byref(m))
            k32.SetConsoleMode(h, m.value | ENABLE_VT)
    except Exception:
        pass

    print(f"Connecting to {user}@{host}  (tmux: {session}) ...")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username=user, password=password,
                       look_for_keys=False, allow_agent=False,
                       timeout=15, banner_timeout=20, auth_timeout=10)
    except Exception as e:
        print(f"\nConnection failed: {e}")
        input("Press Enter to exit.")
        sys.exit(1)

    try:
        cols = os.get_terminal_size().columns
        rows = os.get_terminal_size().lines
    except Exception:
        cols, rows = 220, 50

    chan = client.invoke_shell(term="xterm-256color", width=cols, height=rows)
    chan.send(f"tmux attach-session -t {session}\n")

    stop = threading.Event()

    def recv():
        while not stop.is_set():
            try:
                data = chan.recv(8192)
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except Exception:
                break
        stop.set()

    def send():
        import msvcrt
        while not stop.is_set():
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    if ch in (b'\x00', b'\xe0'):
                        seq = SPECIAL_KEYS.get(msvcrt.getch(), b'')
                        if seq:
                            chan.send(seq)
                    else:
                        chan.send(ch)
                except Exception:
                    stop.set()
                    break
            else:
                time.sleep(0.01)

    threading.Thread(target=recv, daemon=True).start()
    threading.Thread(target=send, daemon=True).start()
    stop.wait()

    client.close()
    print("\n\n[Session closed]")
    input("Press Enter to exit.")


if len(sys.argv) == 6 and sys.argv[1] == "--terminal":
    _run_terminal(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    sys.exit(0)

# ──────────────────────────────────────────────────────────────────────────────
# GUI mode
# ──────────────────────────────────────────────────────────────────────────────

import tkinter as tk
from tkinter import scrolledtext
import subprocess

DEFAULTS = {
    "user":     "localadmin",
    "pass":     "ii70mseq",
    "core":     "10.160.101.137",
    "iupf":     "10.160.101.143",
    "psa1":     "10.160.101.148",
    "psa2":     "10.160.101.198",
    "dn":       "10.160.101.145",
    "gnb":      "10.160.101.120",
    "ue":       "10.160.101.121",
    "ue_count": "8",
}


class ColdStartGUI:
    # ── palette ───────────────────────────────────────────────────────────────
    BG      = "#F1F5F9"
    HDR     = "#0F172A"
    HDR_SUB = "#94A3B8"
    CARD    = "#FFFFFF"
    BORDER  = "#CBD5E1"
    TEXT    = "#1E293B"
    SUBTEXT = "#64748B"
    ACCENT  = "#1A1A1A"
    SUCCESS = "#10B981"
    DANGER  = "#EF4444"
    BTN_SEC = "#E2E8F0"
    LOG_BG  = "#F8FAFC"
    C_OK    = "#059669"
    C_WARN  = "#B45309"
    C_ERR   = "#DC2626"
    C_CMD   = "#1A1A1A"
    FONT    = ("Roboto", 10)
    FONT_B  = ("Roboto", 10, "bold")
    FONT_H  = ("Roboto", 17, "bold")
    FONT_LOG= ("Consolas", 10)
    STEPS   = ["I-UPF", "PSA-UPF", "PSA-UPF2", "Free5GC", "gNB", "UE"]

    def __init__(self, root):
        self.root = root
        self.root.title("Network Topology")
        self.root.geometry("700x980")
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)
        self.running = False
        self._locks = {}
        self._terminal_procs = []
        self.fields = {}
        self._step_colors = [self.BORDER] * len(self.STEPS)

        # ── dark header bar ────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=self.HDR, height=76)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        hdr_left = tk.Frame(hdr, bg=self.HDR)
        hdr_left.pack(side="left", padx=24, pady=10)
        tk.Label(hdr_left, text="Network Topology", bg=self.HDR, fg="#FFFFFF",
                 font=self.FONT_H).pack(anchor="w")
        tk.Label(hdr_left, text="5G Network Cold-Start Automation",
                 bg=self.HDR, fg=self.HDR_SUB,
                 font=("Roboto", 9)).pack(anchor="w")

        hdr_right = tk.Frame(hdr, bg=self.HDR)
        hdr_right.pack(side="right", padx=24)
        self.status_dot = tk.Label(hdr_right, text="●", bg=self.HDR,
                                   fg="#334155", font=("Roboto", 24))
        self.status_dot.pack()

        # ── scrollable body ────────────────────────────────────────────────
        body = tk.Frame(root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=22, pady=14)

        # ── credentials ───────────────────────────────────────────────────
        self._section(body, "CREDENTIALS")
        cf = self._card(body)
        self._field(cf, "user", "Username", 0)
        self._pass_entry = self._field(cf, "pass", "Password", 1, show="*")
        # show/hide password toggle
        self._show_pass = False
        def _toggle_pass():
            self._show_pass = not self._show_pass
            self._pass_entry.config(show="" if self._show_pass else "*")
            toggle_btn.config(text="Hide" if self._show_pass else "Show")
        toggle_btn = tk.Button(
            cf, text="Show", font=("Roboto", 8),
            bg=self.BTN_SEC, fg=self.SUBTEXT,
            relief="flat", bd=0, padx=6, pady=2,
            cursor="hand2", command=_toggle_pass
        )
        toggle_btn.grid(row=1, column=2, padx=(0, 12), pady=7, sticky="w")

        # ── core network ──────────────────────────────────────────────────
        self._section(body, "CORE NETWORK")
        nf = self._card(body)
        self._field(nf, "core", "free5gc Core", 0)
        self._field(nf, "iupf", "I-UPF",        1)
        self._field(nf, "psa1", "PSA-UPF-A",    2)
        self._field(nf, "psa2", "PSA-UPF-B",    3)
        self._field(nf, "dn",   "DN Server",     4)

        # ── RAN ───────────────────────────────────────────────────────────
        self._section(body, "UERANSIM RAN")
        rf = self._card(body)
        self._field(rf, "gnb",      "gNB",      0)
        self._field(rf, "ue",       "UE Host",  1)
        self._field(rf, "ue_count", "UE Count", 2)

        # ── startup step progress ──────────────────────────────────────────
        self._section(body, "STARTUP PROGRESS")
        step_card = self._card(body, inner_pady=14)
        self.step_canvas = tk.Canvas(step_card, bg=self.CARD, height=52,
                                     highlightthickness=0)
        self.step_canvas.pack(fill="x", padx=18)
        self.step_canvas.bind("<Configure>", lambda _: self._draw_steps())
        self.root.after(50, self._draw_steps)

        # ── buttons ───────────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=self.BG)
        btn_row.pack(fill="x", pady=(14, 4))

        self.start_btn = tk.Button(
            btn_row, text="▶   Start Testbed",
            font=("Roboto", 11, "bold"),
            bg=self.ACCENT, fg="#FFFFFF",
            activebackground="#333333", activeforeground="#FFFFFF",
            relief="flat", bd=0, pady=13, cursor="hand2", command=self.start
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.stop_btn = tk.Button(
            btn_row, text="■   Stop",
            font=("Roboto", 11, "bold"),
            bg=self.BTN_SEC, fg=self.SUBTEXT,
            activebackground="#CBD5E1", activeforeground=self.TEXT,
            relief="flat", bd=0, pady=13, cursor="hand2",
            command=self.stop, state="disabled"
        )
        self.stop_btn.pack(side="right", expand=False, padx=(8, 0))
        self.stop_btn.config(width=10)

        # ── status line ───────────────────────────────────────────────────
        self.progress_var = tk.StringVar(value="")
        tk.Label(body, textvariable=self.progress_var, bg=self.BG,
                 fg=self.SUBTEXT, font=("Roboto", 9),
                 anchor="w").pack(fill="x", pady=(4, 8))

        # ── log ───────────────────────────────────────────────────────────
        log_hdr = tk.Frame(body, bg=self.BG)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="LOG", bg=self.BG, fg=self.SUBTEXT,
                 font=("Roboto", 8, "bold")).pack(side="left")

        log_outer = tk.Frame(body, bg=self.BORDER, bd=1)
        log_outer.pack(fill="both", expand=True, pady=(4, 0))
        self.output = scrolledtext.ScrolledText(
            log_outer, bg=self.LOG_BG, fg=self.TEXT,
            font=self.FONT_LOG, relief="flat", borderwidth=8,
            insertbackground=self.TEXT, selectbackground="#D1D5DB"
        )
        self.output.pack(fill="both", expand=True)
        self.output.tag_config("ok",   foreground=self.C_OK)
        self.output.tag_config("warn", foreground=self.C_WARN)
        self.output.tag_config("err",  foreground=self.C_ERR)
        self.output.tag_config("cmd",  foreground=self.C_CMD)

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _section(self, parent, text):
        row = tk.Frame(parent, bg=self.BG)
        row.pack(fill="x", pady=(12, 4))
        tk.Frame(row, bg=self.ACCENT, width=3).pack(side="left", fill="y", padx=(0, 8))
        tk.Label(row, text=text, bg=self.BG, fg=self.TEXT,
                 font=("Roboto", 8, "bold")).pack(side="left")

    def _card(self, parent, inner_pady=0):
        outer = tk.Frame(parent, bg=self.BORDER, bd=1)
        outer.pack(fill="x", pady=(0, 4))
        inner = tk.Frame(outer, bg=self.CARD, pady=inner_pady)
        inner.pack(fill="both", padx=1, pady=1)
        inner.columnconfigure(1, weight=1)
        return inner

    def _field(self, parent, key, label, row, show=""):
        tk.Label(parent, text=label, bg=self.CARD, fg=self.SUBTEXT,
                 font=("Roboto", 9), width=14, anchor="e").grid(
            row=row, column=0, sticky="e", padx=(12, 8), pady=7)
        var = tk.StringVar(value=DEFAULTS.get(key, ""))
        entry = tk.Entry(parent, textvariable=var, show=show,
                         font=self.FONT, bg="#F8FAFC", fg=self.TEXT,
                         relief="flat", bd=0, insertbackground=self.TEXT,
                         highlightthickness=1,
                         highlightbackground=self.BORDER,
                         highlightcolor=self.ACCENT)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=7)
        parent.columnconfigure(1, weight=1)
        self.fields[key] = var
        return entry

    def _add_field(self, parent, key, label, row, show=""):
        self._field(parent, key, label, row, show)

    # ── step progress dots ────────────────────────────────────────────────────

    def _draw_steps(self):
        c = self.step_canvas
        c.delete("all")
        w = c.winfo_width()
        if w < 10:
            return
        n = len(self.STEPS)
        col_w = w / n
        r = 9
        for i, label in enumerate(self.STEPS):
            x = col_w * i + col_w / 2
            cy = 20
            if i < n - 1:
                nx = col_w * (i + 1) + col_w / 2
                line_color = self.SUCCESS if i < len(self._step_colors) and \
                    self._step_colors[i] == self.SUCCESS else self.BORDER
                c.create_line(x + r + 2, cy, nx - r - 2, cy,
                              fill=line_color, width=2)
            fill = self._step_colors[i] if i < len(self._step_colors) else self.BORDER
            c.create_oval(x - r, cy - r, x + r, cy + r, fill=fill, outline="")
            if fill in (self.SUCCESS, self.ACCENT):
                c.create_text(x, cy, text="✓" if fill == self.SUCCESS else str(i + 1),
                              fill="#FFFFFF", font=("Roboto", 8, "bold"))
            c.create_text(x, cy + r + 8, text=label,
                          font=("Roboto", 7), fill=self.SUBTEXT, anchor="n")

    def _set_step(self, idx):
        self._step_colors = [
            self.SUCCESS if i < idx else (self.ACCENT if i == idx else self.BORDER)
            for i in range(len(self.STEPS))
        ]
        self.root.after(0, self._draw_steps)

    def get(self, key):
        return self.fields[key].get()

    def log(self, msg, tag=""):
        def _do():
            self.output.insert("end", msg + "\n", tag)
            self.output.see("end")
        self.root.after(0, _do)

    def set_progress(self, msg):
        def _do():
            self.progress_var.set(msg)
        self.root.after(0, _do)

    # ── SSH helpers ───────────────────────────────────────────────────────────

    def _get_lock(self, host):
        lk = self._locks.get(host)
        if lk is None:
            lk = threading.Lock()
            self._locks[host] = lk
        return lk

    def _new_client(self, host):
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(host, username=self.get("user"), password=self.get("pass"),
                  timeout=10, look_for_keys=False, allow_agent=False,
                  banner_timeout=20, auth_timeout=10)
        return c

    def rssh(self, host, cmd, label="", timeout=300):
        """Run a command on host — plain exec channel, no PTY."""
        if not self.running:
            return False, ""
        if label:
            self.log(f"  [{host}] {label}", "cmd")
        attempts, delay = 4, 1.0
        lock = self._get_lock(host)
        for attempt in range(1, attempts + 1):
            client = None
            try:
                with lock:
                    client = self._new_client(host)
                    _, stdout, stderr = client.exec_command(cmd.strip(), timeout=timeout)
                    out     = stdout.read().decode("utf-8", errors="replace").strip()
                    err_out = stderr.read().decode("utf-8", errors="replace").strip()
                    exit_code = stdout.channel.recv_exit_status()
                    for line in out.splitlines():
                        if "[sudo]" not in line and "password" not in line.lower():
                            self.log(f"    {line}")
                    if exit_code != 0 and err_out:
                        for line in err_out.splitlines()[:3]:
                            if "[sudo]" not in line and "password" not in line.lower():
                                self.log(f"    {line}", "warn")
                    try:
                        client.close()
                    except Exception:
                        pass
                    return exit_code == 0, out
            except Exception as e:
                self.log(f"    ERROR (attempt {attempt}): {e}", "err")
                try:
                    if client:
                        client.close()
                except Exception:
                    pass
                time.sleep(delay)
                delay *= 1.5
        return False, ""

    # ── Service launcher ──────────────────────────────────────────────────────

    def _start_service(self, host, session_name, steps, window_title):
        """
        steps: list of (text, delay_seconds).
        '__PASSWORD__' is replaced with the real password before being typed.
        Uses tmux send-keys so every keystroke (including the sudo password) is
        delivered exactly as if a human typed it into the terminal.
        """
        if not self.running:
            return False

        p = self.get("pass")

        try:
            client = self._new_client(host)
            client.exec_command(f"tmux kill-session -t {session_name} 2>/dev/null")
            time.sleep(0.4)
            # Start a plain bash session — no embedded command, no quoting issues
            client.exec_command(
                f"tmux new-session -d -s {session_name}"
            )[1].channel.recv_exit_status()
            time.sleep(0.5)
            # Type each step into the pane
            for text, delay in steps:
                if text == "__PASSWORD__":
                    text = p
                escaped = text.replace("'", r"'\''")
                client.exec_command(
                    f"tmux send-keys -t {session_name} '{escaped}' Enter"
                )
                time.sleep(delay)
            client.close()
        except Exception as e:
            self.log(f"    ERROR starting {window_title}: {e}", "err")
            return False

        time.sleep(0.5)
        self._open_terminal_window(window_title, host, session_name)
        return True

    def _open_terminal_window(self, title, host, session_name):
        """Spawn a new cmd.exe that runs this same script in --terminal mode."""
        script   = os.path.abspath(__file__)
        user     = self.get("user")
        password = self.get("pass")
        try:
            proc = subprocess.Popen(
                f'start "{title}" cmd /k python "{script}" --terminal {host} {user} {password} {session_name}',
                shell=True
            )
            self._terminal_procs.append(proc)
        except Exception as e:
            self.log(f"    Could not open terminal for {title}: {e}", "warn")

    def _sleep(self, secs):
        for _ in range(secs * 10):
            if not self.running:
                return
            time.sleep(0.1)

    # ── Startup sequence ──────────────────────────────────────────────────────

    def run_sequence(self):
        p    = self.get("pass")
        sudo = f"echo {p} | sudo -S"   # used only for iptables / ip-route rssh calls

        core = self.get("core")
        iupf = self.get("iupf")
        psa1 = self.get("psa1")
        psa2 = self.get("psa2")
        dn   = self.get("dn")
        gnb  = self.get("gnb")
        ue   = self.get("ue")
        n_ue = self.get("ue_count")

        # ── Step 1: I-UPF ─────────────────────────────────────────────────────
        if not self.running: return
        self._set_step(0); self.set_progress("Step 1/6 — I-UPF")
        self.log(f"[Step 1/6] I-UPF on {iupf}", "warn")
        self.rssh(iupf, f"""
{sudo} iptables -t nat -C POSTROUTING -s 10.60.0.0/16 -o ens18 -j MASQUERADE 2>/dev/null || \
{sudo} iptables -t nat -A POSTROUTING -s 10.60.0.0/16 -o ens18 -j MASQUERADE
{sudo} iptables -t nat -C POSTROUTING -s 10.61.0.0/16 -o ens18 -j MASQUERADE 2>/dev/null || \
{sudo} iptables -t nat -A POSTROUTING -s 10.61.0.0/16 -o ens18 -j MASQUERADE
{sudo} ip route add {dn}/32 dev ens18 2>/dev/null || true
{sudo} pkill -9 -f './upf -c' 2>/dev/null || true
sleep 0.5
{sudo} ip link delete upfgtp 2>/dev/null || true
{sudo} rmmod gtp5g 2>/dev/null || true
sleep 0.3
""", "iptables + routes + cleanup")
        self._start_service(iupf, "upf", [
            ("sudo ip link delete upfgtp 2>/dev/null", 1.5),
            ("__PASSWORD__",                           0.3),
            ("cd ~/gtp5g/go-upf",                     0.3),
            ("sudo ./upf -c upfcfg.yaml",             1.5),
            ("__PASSWORD__",                           0.3),
        ], f"I-UPF  [{iupf}]")
        self.log("  ✓ I-UPF started", "ok")
        self._sleep(3)

        # ── Step 2: PSA-UPF ───────────────────────────────────────────────────
        if not self.running: return
        self._set_step(1); self.set_progress("Step 2/6 — PSA-UPF")
        self.log(f"[Step 2/6] PSA-UPF on {psa1}", "warn")
        self.rssh(psa1, f"""
{sudo} iptables -t nat -C POSTROUTING -s 10.60.0.0/16 -o ens18 -j MASQUERADE 2>/dev/null || \
{sudo} iptables -t nat -A POSTROUTING -s 10.60.0.0/16 -o ens18 -j MASQUERADE
{sudo} iptables -t nat -C POSTROUTING -s 10.61.0.0/16 -o ens18 -j MASQUERADE 2>/dev/null || \
{sudo} iptables -t nat -A POSTROUTING -s 10.61.0.0/16 -o ens18 -j MASQUERADE
{sudo} ip route add {dn}/32 dev ens18 2>/dev/null || true
{sudo} pkill -9 -f './upf -c' 2>/dev/null || true
sleep 0.5
{sudo} ip link delete upfgtp 2>/dev/null || true
{sudo} rmmod gtp5g 2>/dev/null || true
sleep 0.3
""", "iptables + routes + cleanup")
        self._start_service(psa1, "upf", [
            ("sudo ip link delete upfgtp 2>/dev/null", 1.5),
            ("__PASSWORD__",                           0.3),
            ("cd ~/gtp5g/go-upf",                     0.3),
            ("sudo ./upf -c upfcfg.yaml",             1.5),
            ("__PASSWORD__",                           0.3),
        ], f"PSA-UPF  [{psa1}]")
        self.log("  ✓ PSA-UPF started", "ok")
        self._sleep(3)

        # ── Step 3: PSA-UPF2 ──────────────────────────────────────────────────
        if not self.running: return
        self._set_step(2); self.set_progress("Step 3/6 — PSA-UPF2")
        self.log(f"[Step 3/6] PSA-UPF2 on {psa2}", "warn")
        self.rssh(psa2, f"""
{sudo} iptables -t nat -C POSTROUTING -s 10.60.0.0/16 -o ens18 -j MASQUERADE 2>/dev/null || \
{sudo} iptables -t nat -A POSTROUTING -s 10.60.0.0/16 -o ens18 -j MASQUERADE
{sudo} iptables -t nat -C POSTROUTING -s 10.61.0.0/16 -o ens18 -j MASQUERADE 2>/dev/null || \
{sudo} iptables -t nat -A POSTROUTING -s 10.61.0.0/16 -o ens18 -j MASQUERADE
{sudo} ip route add {dn}/32 dev ens18 2>/dev/null || true
{sudo} pkill -9 -f './upf -c' 2>/dev/null || true
sleep 0.5
{sudo} ip link delete upfgtp 2>/dev/null || true
{sudo} rmmod gtp5g 2>/dev/null || true
sleep 0.3
""", "iptables + routes + cleanup")
        self._start_service(psa2, "upf", [
            ("sudo ip link delete upfgtp 2>/dev/null", 1.5),
            ("__PASSWORD__",                           0.3),
            ("cd ~/gtp5g/go-upf",                     0.3),
            ("sudo ./upf -c upfcfg.yaml",             1.5),
            ("__PASSWORD__",                           0.3),
        ], f"PSA-UPF2  [{psa2}]")
        self.log("  ✓ PSA-UPF2 started", "ok")
        self._sleep(3)

        # ── Step 4: free5gc (build.sh) ────────────────────────────────────────
        if not self.running: return
        self._set_step(3); self.set_progress("Step 4/6 — Free5GC")
        self.log(f"[Step 4/6] free5gc on {core} — running build.sh", "warn")
        self._start_service(core, "S", [
            ("cd ~/free5gc",    0.3),
            ("sudo ./build.sh", 1.5),
            ("__PASSWORD__",    0.3),
        ], f"free5gc Core  [{core}]")
        self.log("  ✓ free5gc build.sh launched", "ok")
        self._sleep(5)

        # ── DN routes ─────────────────────────────────────────────────────────
        if not self.running: return
        self.log(f"[DN] Adding routes on {dn}", "warn")
        self.rssh(dn, f"""
{sudo} ip route add 10.60.0.0/16 via {psa1} 2>/dev/null || true
{sudo} ip route add 10.61.0.0/16 via {psa1} 2>/dev/null || true
{sudo} ip route add 10.60.0.0/16 via {psa2} metric 200 2>/dev/null || true
{sudo} ip route add 10.61.0.0/16 via {psa2} metric 200 2>/dev/null || true
""", "ip route add")
        self.log("  ✓ DN routes added", "ok")

        # ── Step 5: gNB ───────────────────────────────────────────────────────
        if not self.running: return
        self._set_step(4); self.set_progress("Step 5/6 — gNB")
        self.log(f"[Step 5/6] gNB on {gnb}", "warn")
        self._start_service(gnb, "gnb", [
            ("cd ~/ueransim/build",                             0.3),
            ("sudo ./nr-gnb -c ../config/free5gc-gnb.yaml",    1.5),
            ("__PASSWORD__",                                    0.3),
        ], f"gNB  [{gnb}]")
        self.log("  ✓ gNB started", "ok")
        self._sleep(3)

        # ── Step 6: UE ────────────────────────────────────────────────────────
        if not self.running: return
        self._set_step(5); self.set_progress("Step 6/6 — UE")
        self.log(f"[Step 6/6] {n_ue} UEs on {ue}", "warn")
        self._start_service(ue, "ue", [
            ("cd ~/ueransim/build",                                        0.3),
            (f"sudo ./nr-ue -c ../config/free5gc-ue.yaml -n {n_ue}",      1.5),
            ("__PASSWORD__",                                               0.3),
        ], f"UE  [{ue}]  x{n_ue}")
        self.log(f"  ✓ {n_ue} UEs started", "ok")
        self._sleep(5)

        # ── Verify ────────────────────────────────────────────────────────────
        if not self.running: return
        self.set_progress("Verifying UE tunnels...")
        self.log("\n[VERIFY] Checking uesimtun interfaces...", "warn")
        self.rssh(ue, "ip -br addr | grep uesimtun", "uesimtun check")

        self._set_step(len(self.STEPS))   # all dots green
        self.log("\nTestbed ready.", "ok")
        self.set_progress("Testbed ready")
        self.root.after(0, lambda: self.status_dot.configure(fg="#10B981"))

        self.running = False
        self.root.after(0, self._reset_buttons)

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def _reset_buttons(self):
        self.start_btn.configure(state="normal", bg=self.ACCENT,
                                 fg="#FFFFFF", text="▶   Start Testbed")
        self.stop_btn.configure(state="disabled", bg=self.BTN_SEC)
        self.status_dot.configure(fg="#334155")
        self._step_colors = [self.BORDER] * len(self.STEPS)
        self._draw_steps()

    def start(self):
        if self.running:
            return
        self.running = True
        self.output.delete("1.0", "end")
        self._terminal_procs.clear()
        self._step_colors = [self.BORDER] * len(self.STEPS)
        self._draw_steps()
        self.start_btn.configure(state="disabled", bg="#333333", text="Running…")
        self.stop_btn.configure(state="normal", bg=self.BTN_SEC)
        self.status_dot.configure(fg="#F59E0B")
        threading.Thread(target=self.run_sequence, daemon=True).start()

    def stop(self):
        self.running = False
        self.log("\nStopped by user.", "err")
        self.set_progress("Stopped")
        self.root.after(0, self._reset_buttons)


if __name__ == "__main__":
    root = tk.Tk()
    app = ColdStartGUI(root)
    root.mainloop()
