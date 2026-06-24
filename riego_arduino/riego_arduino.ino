// riego_arduino.ino
// Desarrollador: Hugo Herrera
// Sistema de Riego Inteligente Automatizado v4.0 - Edge Node

#define PIN_SENSOR A0
#define PIN_RELE 7
#define PIN_LED_AUTO 10
#define PIN_LED_MANUAL 11
#define PIN_LED_RIEGO 12

// Umbrales por defecto (1023 = Completamente Seco, 0 = Agua Líquida)
int umbralSeco = 700;
int umbralHumedo = 400;

bool modoAuto = true;
bool estadoBomba = false;

unsigned long ultimoMuestreo = 0;
const unsigned long intervaloMuestreo = 3000; // Mediciones cada 3 segundos

void setup() {
    Serial.begin(115200); // Baud rate optimizado según requerimientos del informe
    pinMode(PIN_RELE, OUTPUT);
    pinMode(PIN_LED_AUTO, OUTPUT);
    pinMode(PIN_LED_MANUAL, OUTPUT);
    pinMode(PIN_LED_RIEGO, OUTPUT);

    // Apagar la bomba inicialmente (Aislamiento óptico, la mayoría activa con LOW, iniciamos en HIGH)
    digitalWrite(PIN_RELE, HIGH);
    actualizarLeds();
}

void loop() {
    gestionarComandosSerial();

    unsigned long tiempoActual = millis();
    if (tiempoActual - ultimoMuestreo >= intervaloMuestreo) {
        ultimoMuestreo = tiempoActual;
        procesarRiego();
        enviarEstadoJSON();
    }
}

void procesarRiego() {
    int valorRaw = analogRead(PIN_SENSOR);

    if (modoAuto) {
        if (valorRaw >= umbralSeco) {
            estadoBomba = true; // Activar riego si el suelo está seco
        } else if (valorRaw <= umbralHumedo) {
            estadoBomba = false; // Detener riego si alcanzó humedad óptima
        }
    }

    // Actuación física sobre el módulo de relé
    if (estadoBomba) {
        digitalWrite(PIN_RELE, LOW);  // Activa relé
    } else {
        digitalWrite(PIN_RELE, HIGH); // Desactiva relé
    }
    actualizarLeds();
}

int obtenerNivel(int raw) {
    if (raw > 850) return 1; // Muy Seco
    if (raw > 700) return 2; // Seco
    if (raw > 400) return 3; // Óptimo
    if (raw > 250) return 4; // Húmedo
    return 5;                // Muy Húmedo
}

String obtenerTextoNivel(int nivel) {
    switch(nivel) {
        case 1: return "MUY SECO";
        case 2: return "SECO";
        case 3: return "OPTIMO";
        case 4: return "HUMEDO";
        case 5: return "MUY HUMEDO";
        default: return "DESCONOCIDO";
    }
}

void enviarEstadoJSON() {
    int raw = analogRead(PIN_SENSOR);
    int nivel = obtenerNivel(raw);
    String texto = obtenerTextoNivel(nivel);

    // Construcción manual de cadena JSON plano interoperable sobre puerto Serial
    String json = "{";
    json += "\"raw\":" + String(raw) + ",";
    json += "\"nivel\":" + String(nivel) + ",";
    json += "\"texto\":\"" + texto + "\",";
    json += "\"modo\":\"" + String(modoAuto ? "AUTO" : "MANUAL") + "\",";
    json += "\"bomba\":" + String(estadoBomba ? "true" : "false") + ",";
    json += "\"regando\":" + String(estadoBomba ? "true" : "false");
    json += "}";

    Serial.println(json);
}

void gestionarComandosSerial() {
    if (Serial.available() > 0) {
        String comando = Serial.readStringUntil('\n');
        comando.trim();

        if (comando == "GET_JSON" || comando == "ESTADO") {
            enviarEstadoJSON();
        }
        else if (comando == "MODO_AUTO") {
            modoAuto = true;
            procesarRiego();
            enviarEstadoJSON();
        }
        else if (comando == "MODO_MANUAL") {
            modoAuto = false;
            procesarRiego();
            enviarEstadoJSON();
        }
        else if (comando == "BOMBA_ON") {
            if (!modoAuto) {
                estadoBomba = true;
                procesarRiego();
            }
            enviarEstadoJSON();
        }
        else if (comando == "BOMBA_OFF") {
            if (!modoAuto) {
                estadoBomba = false;
                procesarRiego();
            }
            enviarEstadoJSON();
        }
        else if (comando == "TEST") {
            digitalWrite(PIN_RELE, LOW);
            digitalWrite(PIN_LED_RIEGO, HIGH);
            delay(1000);
            procesarRiego();
        }
        else if (comando.startsWith("SET_SECO:")) {
            umbralSeco = comando.substring(9).toInt();
        }
        else if (comando.startsWith("SET_HUMEDO:")) {
            umbralHumedo = comando.substring(11).toInt();
        }
    }
}

void actualizarLeds() {
    if (modoAuto) {
        digitalWrite(PIN_LED_AUTO, HIGH);
        digitalWrite(PIN_LED_MANUAL, LOW);
    } else {
        digitalWrite(PIN_LED_AUTO, LOW);
        digitalWrite(PIN_LED_MANUAL, HIGH);
    }

    if (estadoBomba) {
        digitalWrite(PIN_LED_RIEGO, HIGH);
    } else {
        digitalWrite(PIN_LED_RIEGO, LOW);
    }
}
