"""
Sistema de Riego Inteligente Automatizado v4.0
===============================================
Aplicación Python de control con:
  - Interfaz gráfica Tkinter (1300x750)
  - Comunicación serial con Arduino (PySerial)
  - Servidor HTTP embebido en puerto 8080
  - Almacenamiento histórico en SQLite + CSV
  - API REST para control remoto desde web/móvil

Autores : Hugo Herrera


Diciembre 2025
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import serial
import serial.tools.list_ports
import json
import time
import csv
import sqlite3
import os
import math
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ─────────────────────────────────────────────────────────────
#  CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────────────────────
SERIAL_BAUD      = 9600
HTTP_PORT        = 8080
DB_PATH          = "riego_historico.db"
CSV_PATH         = "riego_historico.csv"
POLL_INTERVAL_MS = 500      # ms entre actualizaciones de GUI
HISTORY_MAX      = 288      # 24h con lecturas cada 5min
WINDOW_SIZE      = "1300x750"

# Paleta de colores (tema oscuro moderno)
BG_COLOR         = "#0f172a"
PANEL_COLOR      = "#1e293b"
CARD_COLOR       = "#334155"
ACCENT_COLOR     = "#3b82f6"
SUCCESS_COLOR    = "#10b981"
WARNING_COLOR    = "#f59e0b"
DANGER_COLOR     = "#ef4444"
TEXT_COLOR       = "#f1f5f9"
TEXT_MUTED       = "#94a3b8"
BORDER_COLOR     = "#475569"

# ─────────────────────────────────────────────────────────────
#  MODELO DE DATOS
# ─────────────────────────────────────────────────────────────
current_data = {
    "humedad":       0,
    "modo":          "MANUAL",
    "bomba":         False,
    "umbral_seco":   700,
    "umbral_humedo": 400,
    "conectado":     False,
    "ultimo_update": None,
}
humidity_history = []   # lista de (timestamp, humedad)
event_log        = []   # lista de strings para la consola


# ─────────────────────────────────────────────────────────────
#  BASE DE DATOS SQLite
# ─────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lecturas (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    NOT NULL,
            humedad   INTEGER NOT NULL,
            modo      TEXT    NOT NULL,
            bomba     INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def guardar_lectura(humedad, modo, bomba):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO lecturas (timestamp, humedad, modo, bomba) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), humedad, modo, int(bomba))
        )
        conn.commit()
        conn.close()
        # También guardar en CSV
        existe = os.path.isfile(CSV_PATH)
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not existe:
                w.writerow(["timestamp", "humedad", "modo", "bomba"])
            w.writerow([datetime.now().isoformat(), humedad, modo, int(bomba)])
    except Exception as e:
        log_event(f"[DB] Error al guardar: {e}")

def log_event(msg):
    ts  = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    event_log.append(line)
    if len(event_log) > 200:
        event_log.pop(0)


# ─────────────────────────────────────────────────────────────
#  MANEJADOR HTTP (API REST local)
# ─────────────────────────────────────────────────────────────
class RiegoHTTPHandler(BaseHTTPRequestHandler):
    """
    Endpoints:
      GET /           → página HTML principal
      GET /status     → JSON estado actual
      GET /set_mode/AUTO|MANUAL
      GET /bomba/on|off
      GET /set_umbral/seco/<val>
      GET /set_umbral/humedo/<val>
    """
    serial_queue = None  # inyectado desde la app

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        if path == "" or path == "/":
            self._serve_html()
        elif path == "/status":
            self._json_response(current_data)
        elif path.startswith("/set_mode/"):
            modo = path.split("/")[-1].upper()
            if modo in ("AUTO", "MANUAL"):
                self._send_command(f"MODO_{modo}")
                self._json_response({"ok": True, "modo": modo})
            else:
                self._json_response({"error": "modo inválido"}, 400)
        elif path == "/bomba/on":
            self._send_command("BOMBA_ON")
            self._json_response({"ok": True, "bomba": "ON"})
        elif path == "/bomba/off":
            self._send_command("BOMBA_OFF")
            self._json_response({"ok": True, "bomba": "OFF"})
        elif path.startswith("/set_umbral/seco/"):
            val = path.split("/")[-1]
            self._send_command(f"SET_SECO:{val}")
            self._json_response({"ok": True, "umbral_seco": val})
        elif path.startswith("/set_umbral/humedo/"):
            val = path.split("/")[-1]
            self._send_command(f"SET_HUMEDO:{val}")
            self._json_response({"ok": True, "umbral_humedo": val})
        else:
            self._json_response({"error": "endpoint no encontrado"}, 404)

    def _send_command(self, cmd):
        if self.serial_queue:
            self.serial_queue.put(cmd)
        log_event(f"[WEB] Comando: {cmd}")

    def _json_response(self, data, code=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        html = build_web_html()
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silenciar logs HTTP en consola


def build_web_html():
    """Genera el HTML responsive para el panel web móvil."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>🌱 Sistema Riego IoT</title>
  <style>
    :root {
      --bg: #0f172a; --panel: #1e293b; --card: #334155;
      --accent: #3b82f6; --success: #10b981; --warn: #f59e0b;
      --danger: #ef4444; --text: #f1f5f9; --muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; }
    header { background: var(--panel); padding: 16px 20px; border-bottom: 1px solid #334155;
             display: flex; align-items: center; gap: 10px; }
    header h1 { font-size: 1.2rem; }
    .status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--success);
                  animation: pulse 1.5s infinite; margin-left: auto; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
            gap: 12px; padding: 16px; }
    .card { background: var(--card); border-radius: 12px; padding: 16px; text-align: center; }
    .card .label { font-size: .75rem; color: var(--muted); text-transform: uppercase;
                   letter-spacing: .05em; margin-bottom: 6px; }
    .card .value { font-size: 2rem; font-weight: 700; }
    .card .sub   { font-size: .8rem; color: var(--muted); margin-top: 4px; }
    .controls { padding: 0 16px 16px; display: grid; gap: 10px; }
    .btn { border: none; border-radius: 10px; padding: 14px; font-size: 1rem; font-weight: 600;
           color: #fff; cursor: pointer; transition: opacity .2s; }
    .btn:active { opacity: .75; }
    .btn-auto   { background: var(--accent); }
    .btn-manual { background: var(--warn); }
    .btn-on     { background: var(--success); }
    .btn-off    { background: var(--danger); }
    .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    #log { background: var(--panel); margin: 0 16px 16px; border-radius: 10px;
           padding: 12px; font-family: monospace; font-size: .75rem; color: var(--muted);
           height: 120px; overflow-y: auto; }
  </style>
</head>
<body>
  <header>
    <span>🌱</span>
    <h1>Sistema Riego IoT</h1>
    <div class="status-dot" id="dot"></div>
  </header>

  <div class="grid">
    <div class="card">
      <div class="label">Humedad</div>
      <div class="value" id="hum">—</div>
      <div class="sub">valor ADC (0-1023)</div>
    </div>
    <div class="card">
      <div class="label">Modo</div>
      <div class="value" style="font-size:1.4rem" id="modo">—</div>
    </div>
    <div class="card">
      <div class="label">Bomba</div>
      <div class="value" id="bomba">—</div>
    </div>
  </div>

  <div class="controls">
    <div class="row-2">
      <button class="btn btn-auto"   onclick="cmd('/set_mode/AUTO')">🤖 AUTO</button>
      <button class="btn btn-manual" onclick="cmd('/set_mode/MANUAL')">🖐 MANUAL</button>
    </div>
    <div class="row-2">
      <button class="btn btn-on"  onclick="cmd('/bomba/on')">💧 Riego ON</button>
      <button class="btn btn-off" onclick="cmd('/bomba/off')">⛔ Riego OFF</button>
    </div>
  </div>

  <div id="log">Conectando...</div>

  <script>
    async function fetchStatus() {
      try {
        const r = await fetch('/status');
        const d = await r.json();
        document.getElementById('hum').textContent   = d.humedad ?? '—';
        document.getElementById('modo').textContent  = d.modo    ?? '—';
        document.getElementById('bomba').textContent = d.bomba ? '💧 ON' : '⭕ OFF';
        document.getElementById('dot').style.background = d.conectado ? '#10b981' : '#ef4444';
        addLog(`Estado: H=${d.humedad} Modo=${d.modo} Bomba=${d.bomba?'ON':'OFF'}`);
      } catch(e) { addLog('Error al conectar...'); }
    }
    async function cmd(path) {
      try { await fetch(path); addLog('Comando enviado: ' + path); } 
      catch(e) { addLog('Error: ' + e); }
    }
    function addLog(msg) {
      const el = document.getElementById('log');
      const now = new Date().toLocaleTimeString();
      el.innerHTML += `[${now}] ${msg}\\n`;
      el.scrollTop = el.scrollHeight;
    }
    fetchStatus();
    setInterval(fetchStatus, 3000);
  </script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  WIDGETS PERSONALIZADOS
# ─────────────────────────────────────────────────────────────
class ModernButton(tk.Canvas):
    """Botón con estilo moderno y efecto hover."""
    def __init__(self, parent, text, command, color=ACCENT_COLOR,
                 width=160, height=44, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=PANEL_COLOR, highlightthickness=0, **kwargs)
        self.command = command
        self.color   = color
        self.text    = text
        self._draw(color)
        self.bind("<Enter>",    lambda e: self._draw(self._lighten(color)))
        self.bind("<Leave>",    lambda e: self._draw(color))
        self.bind("<Button-1>", lambda e: command())

    def _lighten(self, hex_color):
        r, g, b = int(hex_color[1:3],16), int(hex_color[3:5],16), int(hex_color[5:7],16)
        r = min(255, r + 30); g = min(255, g + 30); b = min(255, b + 30)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _draw(self, color):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        r = 8
        self.create_rectangle(r, 0, w-r, h, fill=color, outline="")
        self.create_rectangle(0, r, w, h-r, fill=color, outline="")
        for cx, cy in [(r,r),(w-r,r),(r,h-r),(w-r,h-r)]:
            self.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="")
        self.create_text(w//2, h//2, text=self.text, fill=TEXT_COLOR,
                         font=("Segoe UI", 10, "bold"))


class WaterLevelIndicator(tk.Canvas):
    """Indicador circular animado del nivel de humedad."""
    def __init__(self, parent, size=180, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=PANEL_COLOR, highlightthickness=0, **kwargs)
        self.size    = size
        self.percent = 0
        self._draw()

    def set_value(self, raw_value):
        """raw_value: 0-1023 donde 0=agua, 1023=seco → invertimos para % humedad."""
        self.percent = max(0, min(100, round((1023 - raw_value) / 10.23)))
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        cx, cy = s//2, s//2
        r = s//2 - 10

        # Fondo del arco
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=-220, extent=260,
                        style="arc", outline=CARD_COLOR, width=14)

        # Arco de progreso
        if self.percent > 0:
            ext   = self.percent / 100 * 260
            color = SUCCESS_COLOR if self.percent > 40 else \
                    WARNING_COLOR if self.percent > 20 else DANGER_COLOR
            self.create_arc(cx-r, cy-r, cx+r, cy+r,
                            start=-220, extent=ext,
                            style="arc", outline=color, width=14)

        # Texto central
        self.create_text(cx, cy - 10, text=f"{self.percent}%",
                         fill=TEXT_COLOR, font=("Segoe UI", 24, "bold"))
        self.create_text(cx, cy + 18, text="Humedad",
                         fill=TEXT_MUTED, font=("Segoe UI", 10))


class HumidityChart(tk.Canvas):
    """Gráfico de línea con las últimas 24h de humedad."""
    def __init__(self, parent, width=580, height=160, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=CARD_COLOR, highlightthickness=0, **kwargs)
        self.w = width
        self.h = height
        self._draw([])

    def update_data(self, history):
        self._draw(history)

    def _draw(self, history):
        self.delete("all")
        pad = 30
        w, h = self.w, self.h

        # Fondo y grid
        self.create_rectangle(0, 0, w, h, fill=CARD_COLOR, outline="")
        for i in range(5):
            y = pad + (h - 2*pad) * i // 4
            self.create_line(pad, y, w-pad, y, fill=BORDER_COLOR, dash=(3,3))
            pct = 100 - i*25
            self.create_text(pad-4, y, text=f"{pct}%", fill=TEXT_MUTED,
                             font=("Segoe UI", 7), anchor="e")

        # Etiqueta
        self.create_text(w//2, 10, text="Historial de Humedad (24h)",
                         fill=TEXT_MUTED, font=("Segoe UI", 8))

        if len(history) < 2:
            self.create_text(w//2, h//2, text="Sin datos suficientes",
                             fill=TEXT_MUTED, font=("Segoe UI", 10))
            return

        # Convertir valores a coordenadas
        pts  = []
        n    = len(history)
        for i, (_, val) in enumerate(history):
            pct = (1023 - val) / 10.23
            x   = pad + (w - 2*pad) * i / (n - 1)
            y   = pad + (h - 2*pad) * (1 - pct/100)
            pts.append((x, y))

        # Área rellena
        poly = [pad, h-pad] + [c for p in pts for c in p] + [w-pad, h-pad]
        self.create_polygon(*poly, fill="#1e40af", outline="", stipple="gray25")

        # Línea
        for i in range(len(pts)-1):
            self.create_line(*pts[i], *pts[i+1], fill=ACCENT_COLOR, width=2, smooth=True)

        # Punto actual
        if pts:
            lx, ly = pts[-1]
            self.create_oval(lx-4, ly-4, lx+4, ly+4, fill=ACCENT_COLOR, outline=TEXT_COLOR)


# ─────────────────────────────────────────────────────────────
#  APLICACIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────
class SistemaRiegoApp:
    def __init__(self, root):
        self.root      = root
        self.serial_q  = queue.Queue()   # Comandos a enviar al Arduino
        self.data_q    = queue.Queue()   # Datos recibidos del Arduino
        self.ser       = None
        self.http_srv  = None
        self._setup_window()
        self._build_ui()
        self._start_http_server()
        init_db()
        self._update_ui()

    # ── Ventana ───────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("Sistema de Riego Inteligente v4.0 — DUOC UC")
        self.root.geometry(WINDOW_SIZE)
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self.root, bg=PANEL_COLOR, height=52)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🌱  Sistema de Riego Inteligente  v4.0",
                 bg=PANEL_COLOR, fg=TEXT_COLOR,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(hdr, text="DUOC UC · Hugo Herrera & Brandon Varas",
                 bg=PANEL_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side="right", padx=16)

        # ── Body ──
        body = tk.Frame(self.root, bg=BG_COLOR)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Columna izquierda
        left = tk.Frame(body, bg=BG_COLOR)
        left.pack(side="left", fill="y", padx=(0,10))
        self._build_connection_panel(left)
        self._build_indicator(left)
        self._build_controls(left)

        # Columna derecha
        right = tk.Frame(body, bg=BG_COLOR)
        right.pack(side="left", fill="both", expand=True)
        self._build_stats_cards(right)
        self._build_chart(right)
        self._build_log(right)

    def _build_connection_panel(self, parent):
        f = tk.Frame(parent, bg=PANEL_COLOR, bd=0, relief="flat")
        f.pack(fill="x", pady=(0,8))
        tk.Label(f, text="Conexión Serial", bg=PANEL_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10, pady=(8,2))

        row = tk.Frame(f, bg=PANEL_COLOR)
        row.pack(fill="x", padx=10, pady=(0,8))

        self.port_var = tk.StringVar()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb  = ttk.Combobox(row, textvariable=self.port_var,
                                     values=ports, width=10, state="readonly")
        if ports:
            self.port_cb.current(0)
        self.port_cb.pack(side="left")

        self.conn_btn = ModernButton(row, "Conectar", self._toggle_connection,
                                    color=SUCCESS_COLOR, width=90, height=30)
        self.conn_btn.pack(side="left", padx=(6,0))

        self.status_lbl = tk.Label(f, text="● Desconectado", bg=PANEL_COLOR,
                                   fg=DANGER_COLOR, font=("Segoe UI", 8, "bold"))
        self.status_lbl.pack(anchor="w", padx=10, pady=(0,8))

    def _build_indicator(self, parent):
        f = tk.Frame(parent, bg=PANEL_COLOR)
        f.pack(pady=(0,8))
        self.indicator = WaterLevelIndicator(f)
        self.indicator.pack(padx=14, pady=10)

    def _build_controls(self, parent):
        f = tk.Frame(parent, bg=PANEL_COLOR)
        f.pack(fill="x", pady=(0,8))
        tk.Label(f, text="Control", bg=PANEL_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10, pady=(8,4))

        ModernButton(f, "🤖  Modo AUTO",   self._set_auto,   ACCENT_COLOR).pack(padx=10, pady=3)
        ModernButton(f, "🖐  Modo MANUAL", self._set_manual, WARNING_COLOR).pack(padx=10, pady=3)
        ModernButton(f, "💧  Riego ON",    self._bomba_on,   SUCCESS_COLOR).pack(padx=10, pady=3)
        ModernButton(f, "⛔  Riego OFF",   self._bomba_off,  DANGER_COLOR).pack(padx=10, pady=(3,6))

        # Sliders umbrales
        tk.Label(f, text="Umbral Seco", bg=PANEL_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        self.sl_seco = tk.Scale(f, from_=300, to=1023, orient="horizontal",
                                bg=PANEL_COLOR, fg=TEXT_COLOR, troughcolor=CARD_COLOR,
                                highlightthickness=0, command=self._on_seco_change)
        self.sl_seco.set(700)
        self.sl_seco.pack(fill="x", padx=10)

        tk.Label(f, text="Umbral Húmedo", bg=PANEL_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        self.sl_humedo = tk.Scale(f, from_=0, to=700, orient="horizontal",
                                  bg=PANEL_COLOR, fg=TEXT_COLOR, troughcolor=CARD_COLOR,
                                  highlightthickness=0, command=self._on_humedo_change)
        self.sl_humedo.set(400)
        self.sl_humedo.pack(fill="x", padx=10, pady=(0,10))

    def _build_stats_cards(self, parent):
        row = tk.Frame(parent, bg=BG_COLOR)
        row.pack(fill="x", pady=(0,8))
        self.cards = {}
        specs = [
            ("humedad_raw", "Valor ADC",       "—",        ACCENT_COLOR),
            ("modo",        "Modo",             "MANUAL",   WARNING_COLOR),
            ("bomba",       "Bomba",            "OFF",      DANGER_COLOR),
            ("umbral_s",    "Umbral Seco",      "700",      TEXT_MUTED),
            ("umbral_h",    "Umbral Húmedo",    "400",      TEXT_MUTED),
            ("tiempo",      "Última Lectura",   "—",        TEXT_MUTED),
        ]
        for key, label, default, color in specs:
            card = tk.Frame(row, bg=CARD_COLOR, bd=0)
            card.pack(side="left", expand=True, fill="both", padx=3, ipady=6)
            tk.Label(card, text=label, bg=CARD_COLOR, fg=TEXT_MUTED,
                     font=("Segoe UI", 7, "bold")).pack()
            lbl = tk.Label(card, text=default, bg=CARD_COLOR, fg=color,
                           font=("Segoe UI", 13, "bold"))
            lbl.pack()
            self.cards[key] = lbl

    def _build_chart(self, parent):
        f = tk.Frame(parent, bg=CARD_COLOR)
        f.pack(fill="x", pady=(0,8))
        self.chart = HumidityChart(f, width=630, height=160)
        self.chart.pack(padx=2, pady=2)

    def _build_log(self, parent):
        f = tk.Frame(parent, bg=PANEL_COLOR)
        f.pack(fill="both", expand=True)
        hdr = tk.Frame(f, bg=PANEL_COLOR)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Consola de eventos", bg=PANEL_COLOR, fg=TEXT_MUTED,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=10, pady=6)
        ModernButton(hdr, "Exportar CSV", self._export_csv,
                     CARD_COLOR, width=110, height=26).pack(side="right", padx=8, pady=6)

        self.log_text = tk.Text(f, bg="#0a0f1a", fg=TEXT_MUTED,
                                font=("Consolas", 8), wrap="word",
                                state="disabled", relief="flat")
        sb = ttk.Scrollbar(f, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=(0,4))

    # ── Bucle de actualización de UI ─────────────────────────
    def _update_ui(self):
        # Procesar datos del Arduino
        while not self.data_q.empty():
            raw = self.data_q.get()
            self._process_arduino_data(raw)

        # Actualizar widgets
        d = current_data
        pct = max(0, min(100, round((1023 - d["humedad"]) / 10.23)))
        self.indicator.set_value(d["humedad"])

        self.cards["humedad_raw"].config(text=str(d["humedad"]))
        self.cards["modo"].config(text=d["modo"],
            fg=ACCENT_COLOR if d["modo"]=="AUTO" else WARNING_COLOR)
        self.cards["bomba"].config(text="💧 ON" if d["bomba"] else "⭕ OFF",
            fg=SUCCESS_COLOR if d["bomba"] else DANGER_COLOR)
        self.cards["umbral_s"].config(text=str(d["umbral_seco"]))
        self.cards["umbral_h"].config(text=str(d["umbral_humedo"]))
        if d["ultimo_update"]:
            self.cards["tiempo"].config(text=d["ultimo_update"].strftime("%H:%M:%S"))

        self.chart.update_data(humidity_history[-HISTORY_MAX:])

        # Actualizar consola
        if event_log:
            self.log_text.config(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("end", "\n".join(event_log[-80:]))
            self.log_text.see("end")
            self.log_text.config(state="disabled")

        self.root.after(POLL_INTERVAL_MS, self._update_ui)

    def _process_arduino_data(self, raw_line):
        raw_line = raw_line.strip()
        if raw_line.startswith("{"):
            try:
                d = json.loads(raw_line)
                current_data.update({
                    "humedad":       d.get("humedad",       current_data["humedad"]),
                    "modo":          d.get("modo",          current_data["modo"]),
                    "bomba":         d.get("bomba",         current_data["bomba"]),
                    "umbral_seco":   d.get("umbral_seco",   current_data["umbral_seco"]),
                    "umbral_humedo": d.get("umbral_humedo", current_data["umbral_humedo"]),
                    "conectado":     True,
                    "ultimo_update": datetime.now(),
                })
                humidity_history.append((datetime.now(), d.get("humedad", 0)))
                guardar_lectura(d.get("humedad",0), d.get("modo",""), d.get("bomba",False))
                log_event(f"Lectura: H={d.get('humedad')} Modo={d.get('modo')} Bomba={d.get('bomba')}")
            except json.JSONDecodeError:
                log_event(f"JSON inválido: {raw_line}")
        elif raw_line.startswith("#"):
            log_event(raw_line[2:])

    # ── Conexión serial ───────────────────────────────────────
    def _toggle_connection(self):
        if current_data["conectado"]:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("Sin puerto", "Selecciona un puerto COM primero.")
            return
        try:
            self.ser = serial.Serial(port, SERIAL_BAUD, timeout=1)
            current_data["conectado"] = True
            self.status_lbl.config(text=f"● Conectado ({port})", fg=SUCCESS_COLOR)
            self.conn_btn.text = "Desconectar"
            self.conn_btn._draw(DANGER_COLOR)
            log_event(f"Conectado a {port} @ {SERIAL_BAUD} baudios")
            threading.Thread(target=self._serial_reader, daemon=True).start()
            threading.Thread(target=self._serial_writer, daemon=True).start()
        except serial.SerialException as e:
            messagebox.showerror("Error serial", str(e))

    def _disconnect(self):
        if self.ser:
            self.ser.close()
        current_data["conectado"] = False
        self.status_lbl.config(text="● Desconectado", fg=DANGER_COLOR)
        log_event("Desconectado del Arduino.")

    def _serial_reader(self):
        while current_data["conectado"] and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore")
                if line:
                    self.data_q.put(line)
            except Exception:
                break

    def _serial_writer(self):
        while current_data["conectado"] and self.ser and self.ser.is_open:
            try:
                cmd = self.serial_q.get(timeout=0.5)
                self.ser.write((cmd + "\n").encode())
                log_event(f"→ Arduino: {cmd}")
            except queue.Empty:
                pass
            except Exception:
                break

    # ── Comandos de control ───────────────────────────────────
    def _send(self, cmd):
        if not current_data["conectado"]:
            log_event("[!] No conectado al Arduino.")
            return
        self.serial_q.put(cmd)

    def _set_auto(self):    self._send("MODO_AUTO")
    def _set_manual(self):  self._send("MODO_MANUAL")
    def _bomba_on(self):    self._send("BOMBA_ON")
    def _bomba_off(self):   self._send("BOMBA_OFF")

    def _on_seco_change(self, val):
        self._send(f"SET_SECO:{val}")

    def _on_humedo_change(self, val):
        self._send(f"SET_HUMEDO:{val}")

    # ── CSV Export ────────────────────────────────────────────
    def _export_csv(self):
        if not os.path.isfile(CSV_PATH):
            messagebox.showinfo("Sin datos", "No hay historial registrado aún.")
            return
        dest = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV","*.csv")],
                                            initialfile="riego_historico.csv")
        if dest:
            import shutil
            shutil.copy(CSV_PATH, dest)
            messagebox.showinfo("Exportado", f"CSV guardado en:\n{dest}")

    # ── Servidor HTTP ─────────────────────────────────────────
    def _start_http_server(self):
        RiegoHTTPHandler.serial_queue = self.serial_q
        self.http_srv = HTTPServer(("", HTTP_PORT), RiegoHTTPHandler)
        t = threading.Thread(target=self.http_srv.serve_forever, daemon=True)
        t.start()
        log_event(f"Servidor web local en http://localhost:{HTTP_PORT}")


# ─────────────────────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = SistemaRiegoApp(root)
    root.mainloop()
