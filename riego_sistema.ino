/*
 * ============================================================
 *  Sistema de Riego Inteligente Automatizado v4.0

 *  Autor   : Hugo Herrera

 *  Fecha     : Diciembre 2025

 * ============================================================
 *
 *  Hardware:
 *    A0  → Sensor de humedad YL-69
 *    D8  → Módulo Relé  (bomba de agua)
 *    D4  → LED Verde    (modo AUTO activo)
 *    D3  → LED Rojo     (modo MANUAL activo)
 *    D5  → LED Amarillo (bomba encendida)
 *    D10 → Botón Modo   (alterna AUTO/MANUAL)
 *    D6  → Botón Bomba  (activa/desactiva bomba en modo MANUAL)
 *
 *  Protocolo serial: 9600 baudios, 8N1
 *  Comandos recibidos:
 *    GET_JSON        → responde con JSON de estado completo
 *    MODO_AUTO       → activa modo automático
 *    MODO_MANUAL     → activa modo manual
 *    BOMBA_ON        → enciende bomba (solo MANUAL)
 *    BOMBA_OFF       → apaga bomba
 *    SET_SECO:<val>  → cambia umbral seco  (ej: SET_SECO:700)
 *    SET_HUMEDO:<val>→ cambia umbral húmedo (ej: SET_HUMEDO:400)
 * ============================================================
 */

// ── Pines ────────────────────────────────────────────────────
const int PIN_SENSOR    = A0;
const int PIN_RELE      = 8;
const int PIN_LED_AUTO  = 4;
const int PIN_LED_MANUAL= 3;
const int PIN_LED_RIEGO = 5;
const int PIN_BTN_MODO  = 10;
const int PIN_BTN_BOMBA = 6;

// ── Constantes del sistema ───────────────────────────────────
const unsigned long INTERVALO_LECTURA   = 5000;  // ms entre lecturas
const unsigned long DEBOUNCE_DELAY      = 200;   // ms debounce botones
const int           BUFFER_SERIAL       = 64;    // bytes buffer serial

// ── Variables de estado globales ─────────────────────────────
int  humedad          = 0;
bool modoAuto         = true;
bool bombaActiva      = false;
int  umbralSeco       = 700;   // > umbralSeco  → suelo seco  → activar riego
int  umbralHumedo     = 400;   // < umbralHumedo→ suelo húmedo → detener riego

// ── Control de tiempo ────────────────────────────────────────
unsigned long ultimaLectura     = 0;
unsigned long ultimoDebounceM   = 0;  // botón modo
unsigned long ultimoDebouncaB   = 0;  // botón bomba

// ── Buffer de comandos serial ─────────────────────────────────
char   bufferCmd[BUFFER_SERIAL];
int    idxBuffer = 0;

// ─────────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);

  // Configurar pines
  pinMode(PIN_RELE,       OUTPUT);
  pinMode(PIN_LED_AUTO,   OUTPUT);
  pinMode(PIN_LED_MANUAL, OUTPUT);
  pinMode(PIN_LED_RIEGO,  OUTPUT);
  pinMode(PIN_BTN_MODO,   INPUT_PULLUP);
  pinMode(PIN_BTN_BOMBA,  INPUT_PULLUP);

  // Estado inicial: todo apagado
  apagarBomba();
  actualizarLEDs();

  // Mensaje de arranque por serial
  Serial.println(F("# Sistema Riego v4.0 - DUOC UC - Hugo Herrera, Brandon Varas"));
  Serial.println(F("# Listo. Esperando comandos..."));
  enviarJSON();  // enviar estado inicial
}

// ─────────────────────────────────────────────────────────────
//  LOOP PRINCIPAL
// ─────────────────────────────────────────────────────────────
void loop() {
  leerComandosSerial();
  leerBotones();

  // Lectura periódica del sensor
  unsigned long ahora = millis();
  if (ahora - ultimaLectura >= INTERVALO_LECTURA) {
    ultimaLectura = ahora;
    int lecturaAnterior = humedad;
    humedad = analogRead(PIN_SENSOR);

    if (modoAuto) {
      controlAuto();
    }

    // Solo enviar JSON si cambió el estado (ahorra tráfico serial)
    if (abs(humedad - lecturaAnterior) > 5 || bombaActiva != (digitalRead(PIN_RELE) == LOW)) {
      enviarJSON();
    }
  }
}

// ─────────────────────────────────────────────────────────────
//  LÓGICA DE CONTROL
// ─────────────────────────────────────────────────────────────

/**
 * Control automático: activa/desactiva bomba según umbrales.
 * Usa histéresis para evitar conmutaciones rápidas.
 */
void controlAuto() {
  if (humedad > umbralSeco && !bombaActiva) {
    encenderBomba();
  } else if (humedad < umbralHumedo && bombaActiva) {
    apagarBomba();
  }
}

void controlManual() {
  // En modo manual, la bomba solo responde a comandos o al botón físico.
  // Esta función existe para posibles extensiones futuras.
}

void encenderBomba() {
  bombaActiva = true;
  digitalWrite(PIN_RELE, LOW);   // Relé activo en LOW (lógica inversa)
  digitalWrite(PIN_LED_RIEGO, HIGH);
  Serial.println(F("# BOMBA: ON"));
}

void apagarBomba() {
  bombaActiva = false;
  digitalWrite(PIN_RELE, HIGH);  // Relé inactivo en HIGH
  digitalWrite(PIN_LED_RIEGO, LOW);
  Serial.println(F("# BOMBA: OFF"));
}

// ─────────────────────────────────────────────────────────────
//  BOTONES FÍSICOS
// ─────────────────────────────────────────────────────────────
void leerBotones() {
  unsigned long ahora = millis();

  // Botón Modo: alterna AUTO ↔ MANUAL
  if (digitalRead(PIN_BTN_MODO) == LOW && (ahora - ultimoDebounceM) > DEBOUNCE_DELAY) {
    ultimoDebounceM = ahora;
    modoAuto = !modoAuto;
    if (!modoAuto) apagarBomba();  // al entrar a MANUAL, apagar bomba por seguridad
    actualizarLEDs();
    enviarJSON();
    Serial.print(F("# MODO: "));
    Serial.println(modoAuto ? F("AUTO") : F("MANUAL"));
  }

  // Botón Bomba: solo funciona en modo MANUAL
  if (!modoAuto && digitalRead(PIN_BTN_BOMBA) == LOW && (ahora - ultimoDebouncaB) > DEBOUNCE_DELAY) {
    ultimoDebouncaB = ahora;
    if (bombaActiva) {
      apagarBomba();
    } else {
      encenderBomba();
    }
    enviarJSON();
  }
}

// ─────────────────────────────────────────────────────────────
//  COMUNICACIÓN SERIAL
// ─────────────────────────────────────────────────────────────

/**
 * Leer comandos del serial byte a byte hasta '\n'.
 * Comando completo → procesarComando().
 */
void leerComandosSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      bufferCmd[idxBuffer] = '\0';
      procesarComando(bufferCmd);
      idxBuffer = 0;
    } else if (idxBuffer < BUFFER_SERIAL - 1) {
      bufferCmd[idxBuffer++] = c;
    }
  }
}

void procesarComando(const char* cmd) {
  if (strcmp(cmd, "GET_JSON") == 0) {
    enviarJSON();

  } else if (strcmp(cmd, "MODO_AUTO") == 0) {
    modoAuto = true;
    actualizarLEDs();
    enviarJSON();

  } else if (strcmp(cmd, "MODO_MANUAL") == 0) {
    modoAuto = false;
    apagarBomba();
    actualizarLEDs();
    enviarJSON();

  } else if (strcmp(cmd, "BOMBA_ON") == 0) {
    if (!modoAuto) { encenderBomba(); enviarJSON(); }
    else Serial.println(F("# ERROR: BOMBA_ON solo en modo MANUAL"));

  } else if (strcmp(cmd, "BOMBA_OFF") == 0) {
    apagarBomba();
    enviarJSON();

  } else if (strncmp(cmd, "SET_SECO:", 9) == 0) {
    int valor = atoi(cmd + 9);
    if (valor >= 300 && valor <= 1023) {
      umbralSeco = valor;
      Serial.print(F("# UMBRAL_SECO: ")); Serial.println(umbralSeco);
      enviarJSON();
    } else {
      Serial.println(F("# ERROR: Umbral seco fuera de rango (300-1023)"));
    }

  } else if (strncmp(cmd, "SET_HUMEDO:", 11) == 0) {
    int valor = atoi(cmd + 11);
    if (valor >= 0 && valor <= 700) {
      umbralHumedo = valor;
      Serial.print(F("# UMBRAL_HUMEDO: ")); Serial.println(umbralHumedo);
      enviarJSON();
    } else {
      Serial.println(F("# ERROR: Umbral húmedo fuera de rango (0-700)"));
    }

  } else {
    Serial.print(F("# ERROR: Comando desconocido: "));
    Serial.println(cmd);
  }
}

/**
 * Enviar estado completo del sistema en formato JSON por serial.
 * Formato: {"humedad":650,"modo":"AUTO","bomba":false,"umbral_seco":700,"umbral_humedo":400}
 */
void enviarJSON() {
  Serial.print(F("{\"humedad\":"));
  Serial.print(humedad);
  Serial.print(F(",\"modo\":\""));
  Serial.print(modoAuto ? F("AUTO") : F("MANUAL"));
  Serial.print(F("\",\"bomba\":"));
  Serial.print(bombaActiva ? F("true") : F("false"));
  Serial.print(F(",\"umbral_seco\":"));
  Serial.print(umbralSeco);
  Serial.print(F(",\"umbral_humedo\":"));
  Serial.print(umbralHumedo);
  Serial.println(F("}"));
}

// ─────────────────────────────────────────────────────────────
//  INDICADORES LED
// ─────────────────────────────────────────────────────────────
void actualizarLEDs() {
  digitalWrite(PIN_LED_AUTO,   modoAuto  ? HIGH : LOW);
  digitalWrite(PIN_LED_MANUAL, !modoAuto ? HIGH : LOW);
  // LED riego (amarillo) lo gestiona encenderBomba/apagarBomba
}
