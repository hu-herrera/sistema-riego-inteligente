#  Sistema de Riego Inteligente Automatizado v4.0

> Hugo Herrera 

---

##  Descripción

Sistema IoT de riego automático basado en **Arduino + Python** que monitorea la humedad del suelo en tiempo real y activa o desactiva una bomba de agua de forma autónoma. Incluye interfaz gráfica de escritorio y panel web responsive accesible desde cualquier dispositivo de la red local.

Nació como respuesta a la ineficiencia del riego tradicional, que desperdicia hasta el 50% del agua. Funciona **100% local**, sin costos cloud ni dependencia de internet — lección aprendida tras consumir el saldo gratuito de Firebase en menos de 24 horas con lecturas cada 5 segundos.

---

##  Características

| Módulo | Descripción |
|---|---|
|  **Sensor YL-69** | Medición continua de humedad (0–1023 ADC) cada 5 segundos |
|  **Modo AUTO** | Activa/desactiva la bomba automáticamente según umbrales configurables |
|  **Modo MANUAL** | Control directo por botón físico, GUI o panel web |
|  **GUI Tkinter** | Interfaz gráfica 1300×750 con gráfico de 24h, indicador circular y consola |
|  **Panel Web** | Servidor HTTP en puerto 8080, responsive para móvil |
|  **Historial** | Almacenamiento en SQLite + exportación CSV |
|  **LEDs indicadores** | Verde=AUTO · Rojo=MANUAL · Amarillo=Bomba activa |
|  **Botones físicos** | Control directo sin necesidad de PC |

---

##  Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  CAPA 1 · HARDWARE (Edge)                                   │
│  Sensor YL-69 → Arduino Uno → Relé → Bomba 12V DC          │
│  LEDs + Botones físicos                                     │
└───────────────────────┬─────────────────────────────────────┘
                        │ Serial UART 9600 baud (JSON)
┌───────────────────────▼─────────────────────────────────────┐
│  CAPA 2 · SOFTWARE (Fog)                                    │
│  Python 3.11 · Tkinter GUI · PySerial · SQLite              │
│  Algoritmo AUTO/MANUAL · Análisis estadístico               │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP/1.1 puerto 8080
┌───────────────────────▼─────────────────────────────────────┐
│  CAPA 3 · INTERFAZ (Cloud local)                            │
│  Panel web HTML5 responsive · API REST · Control móvil      │
└─────────────────────────────────────────────────────────────┘
```

---

##  Hardware

| Componente | Especificaciones | Pin Arduino |
|---|---|---|
| Arduino Uno R3 | ATmega328P · 16 MHz | — |
| Sensor YL-69 | Capacitivo · 0–1023 ADC | A0 |
| Módulo Relé 5V | 250V/10A · aislamiento óptico | D8 |
| LED Verde | Modo AUTO | D4 |
| LED Rojo | Modo MANUAL | D3 |
| LED Amarillo | Bomba activa | D5 |
| Botón Modo | Alterna AUTO/MANUAL | D10 |
| Botón Bomba | Control manual bomba | D6 |
| Bomba 5V DC | Mini bomba sumergible | Via relé |
| Protoboard 830 | Prototipado | — |

**Costo total del hardware: ~$30 USD**

---

##  Protocolo de Comunicación

### Comandos Serial (Arduino ← Python)

```
GET_JSON          → Solicitar estado completo
MODO_AUTO         → Activar modo automático
MODO_MANUAL       → Activar modo manual
BOMBA_ON          → Encender bomba (solo en MANUAL)
BOMBA_OFF         → Apagar bomba
SET_SECO:700      → Cambiar umbral seco  (300–1023)
SET_HUMEDO:400    → Cambiar umbral húmedo (0–700)
```
*Todos los comandos terminan en `\n`*

### Respuesta JSON (Arduino → Python)

```json
{
  "humedad": 650,
  "modo": "AUTO",
  "bomba": false,
  "umbral_seco": 700,
  "umbral_humedo": 400
}
```

### API REST (puerto 8080)

| Endpoint | Método | Acción |
|---|---|---|
| `/` | GET | Panel web HTML |
| `/status` | GET | JSON estado actual |
| `/set_mode/AUTO` | GET | Cambiar a automático |
| `/set_mode/MANUAL` | GET | Cambiar a manual |
| `/bomba/on` | GET | Activar bomba |
| `/bomba/off` | GET | Desactivar bomba |
| `/set_umbral/seco/700` | GET | Ajustar umbral seco |
| `/set_umbral/humedo/400` | GET | Ajustar umbral húmedo |

---

##  Instalación y Uso

### 1. Arduino
```bash
# Abrir riego_sistema.ino en Arduino IDE 2.x
# Seleccionar: Herramientas → Placa → Arduino Uno
# Seleccionar el puerto COM correcto
# Subir el sketch
```

### 2. Python
```bash
# Clonar el repositorio
git clone https://github.com/TU_USUARIO/sistema-riego-inteligente.git
cd sistema-riego-inteligente

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar la aplicación
python riego_control.py
```

### 3. Panel web
Una vez ejecutando la app, abrir en cualquier navegador de la red local:
```
http://localhost:8080
```

---

##  Estructura del Proyecto

```
sistema-riego-inteligente/
├── riego_sistema.ino   # Firmware Arduino (C++)
├── riego_control.py    # App de control Python (Tkinter + HTTP + SQLite)
├── requirements.txt    # Dependencias Python
└── README.md           # Este archivo
```

---

##  Métricas de Funcionamiento

| Métrica | Resultado | Objetivo |
|---|---|---|
| Precisión sensor | ±5% | ±10% |
| Latencia Arduino→Python | <100 ms | <500 ms |
| Disponibilidad local | 100% | 100% |
| Disponibilidad web | 99.9% | 95% |
| Consumo memoria Python | 45 MB | <100 MB |
| Tiempo respuesta comando | 1.5 s | <3 s |

---

##  Cloud vs Local

| Parámetro | Firebase/AWS | Este sistema |
|---|---|---|
| Costo mensual | $15–$50/dispositivo | **$0** |
| Costo por 100K mensajes | $0.06 | **$0** |
| Dependencia de internet | Total | **Ninguna** |
| Control sobre datos | Limitado | **Completo** |

---

##  Lógica de Control Automático

```
Valor sensor > umbral_seco  (700) → Suelo SECO  → Activar bomba
Valor sensor < umbral_humedo (400) → Suelo HÚMEDO → Detener bomba
400 ≤ valor ≤ 700            → Zona neutra  → Mantener estado actual
```
*(El sensor YL-69 retorna 0 en agua y 1023 en aire seco)*

---

##  Equipo

- **Hugo Herrera** — Hardware, firmware Arduino, software Python, integración completa - Documentación técnica, presentación, testing
