// Firmware do no LoRaWAN — ESP32 Heltec WiFi LoRa 32 V2 + BME280
//
// Base: material da disciplina de Redes de Comunicacao, do professor
// Eduardo Paciencia Godoy (UNESP Sorocaba). O esqueleto LMIC, o tratamento de
// downlink e o uso do display OLED vem de la. O que a Equipe 6 acrescentou:
// leitura do BME280 em barramento I2C separado, payload JSON com chaves curtas,
// modo ABP e fixacao de canal para o gateway de canal unico.
//
// ATENCAO — chaves removidas. Os valores de DEVADDR, NWKSKEY, APPSKEY e APPKEY
// abaixo estao zerados de proposito: sao credenciais da rede LoRaWAN e nao
// entram em repositorio publico. Gere as suas no ChirpStack (instrucoes no
// README desta pasta) antes de compilar.
//
// VERIFIQUE A DOCUMENTACAO para instalar as bibliotecas corretas

#include <lmic.h>
#include <hal/hal.h>
#include <SPI.h>

#include <ArduinoJson.h>
#include <SSD1306.h>      // Driver do display OLED

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
/* BIBLIOTECAS A INSTALAR (Ferramentas → Gerenciar Bibliotecas), as TRÊS:
 *   "Adafruit BME280 Library"
 *   "Adafruit Unified Sensor"
 *   "Adafruit BusIO"          <- esquecida com frequência
 *
 * A IDE oferece instalar as dependências junto, mas se você recusar (ou usar a
 * linha de comando) o erro é "Adafruit_I2CDevice.h: No such file or directory",
 * que não menciona a BusIO em lugar nenhum. */

// Definições do display OLED
#define LEDPIN 25
#define OLED_I2C_ADDR 0x3C
#define OLED_RESET    16
#define OLED_SDA      4
#define OLED_SCL      15
SSD1306 display (OLED_I2C_ADDR, OLED_SDA, OLED_SCL);

/* ==================== SENSOR BME280 ====================
 * O BME280 fica num SEGUNDO barramento I2C (Wire1). O display já ocupa o
 * Wire nos pinos 4/15, e a biblioteca do SSD1306 chama Wire.begin() por conta
 * própria — separar os barramentos evita disputa entre as duas bibliotecas.
 *
 * Ligação:  VCC → 3V3   GND → GND   SDA → GPIO21   SCL → GPIO22
 *
 * Na Heltec V2 o GPIO21 também é a linha de controle do Vext. Funciona como SDA
 * porque este firmware não liga o Vext (não há VCC_ENABLE definido para a V2),
 * mas se você alimentar o sensor pelo Vext em vez do 3V3 fixo, mude o SDA. */
#define BME_SDA   21
#define BME_SCL   22
#define BME_ADDR  0x76      // módulos genéricos usam 0x76; alguns usam 0x77
Adafruit_BME280 bme;
bool bme_ok = false;

/* Intervalo entre leituras, em segundos.
 * Diferente dos sensores Zigbee (que só reportam quando querem), aqui nós
 * escolhemos a cadência. 60 s dá granularidade de sobra para clima e mantém o
 * tempo de ar baixo: em SF7 cada uplink ocupa ~60 ms. Se for alimentar por
 * bateria, subir para 300 s muda pouco no dado e muito na autonomia. */
const unsigned TX_INTERVAL = 60;

// Payload JSON. 128 bytes cobrem com folga os ~30 que realmente usamos.
StaticJsonDocument<128> doc;
static uint8_t payload[64];

/* ==================== CONFIGURAÇÕES LoRaWAN ==================== */
/* DESTINO: ChirpStack rodando na TV Box, alcançado pelo gateway de canal
 * único (Heltec com ESP-1ch-Gateway). Não é mais o TTN.
 *
 * A tríade abaixo precisa bater EXATAMENTE com o gateway e com o ChirpStack.
 * É a causa nº 1 de "tudo parece funcionar mas nenhum pacote chega":
 *
 *   nó (este arquivo)   gateway (configGway.h)   ChirpStack
 *   -----------------   ----------------------   ------------------
 *   canal 8 (916.8MHz)  AU925_928, freq[0]       região "au915_1"
 *   SF7                 _SPREADING SF7           (sub-banda 2)
 */
#define _CANAL_UNICO  8        // canal 8 = 916.8 MHz, o único que o gateway escuta
#define _SF_TRABALHO  DR_SF7   // precisa ser igual ao _SPREADING do gateway

/* ATIVAÇÃO: 0 = OTAA (join pela rede), 1 = ABP (sessão fixa).
 *
 * O OTAA depende de receber o JoinAccept, que é um DOWNLINK — e downlink é o
 * ponto fraco de um gateway de canal único. Se o monitor serial repetir
 * "EV_JOIN_TXCOMPLETE: no JoinAccept", mude para 1 e preencha as três chaves
 * de sessão logo abaixo (o ChirpStack as gera na aba Activation do device). */
#define _USAR_ABP  1

#define freqPlan TTN_FP_AU915 // Plano de frequências
char TTN_response[30];

/* -------- Parâmetros para autenticação OTAA --------
 * Estas chaves precisam ser cadastradas no ChirpStack (Applications → Device).
 * ATENÇÃO à ordem dos bytes: aqui o DevEUI e o JoinEUI estão em LSB, mas a
 * interface do ChirpStack pede MSB — ou seja, invertidos.
 *
 * PREENCHA com os valores do SEU device. Os zeros abaixo não funcionam.
 */
// Application EUI / JoinEUI (LSB)
static const u1_t PROGMEM APPEUI[8]={ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8);}

// Device EUI (LSB) - no ChirpStack, cadastre na ordem inversa
static const u1_t PROGMEM DEVEUI[8]={ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8);}

// Application Key (MSB)
static const u1_t PROGMEM APPKEY[16] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
void os_getDevKey (u1_t* buf) {  memcpy_P(buf, APPKEY, 16);}
/* -------------------------------------------------- */

/* -------- Parâmetros para ativação ABP (só usados se _USAR_ABP == 1) --------
 * Gere estes três valores no ChirpStack: abra o device → aba "Activation" →
 * botão de gerar. Copie os hexadecimais para cá, byte a byte.
 *
 * Todos em MSB, na MESMA ordem em que aparecem na tela do ChirpStack.
 * O DevAddr é um número de 32 bits, escrito de uma vez com 0x na frente.
 *
 * PREENCHA com os valores do SEU device. Os zeros abaixo não funcionam.
 */
static const u4_t DEVADDR = 0x00000000;

static const u1_t PROGMEM NWKSKEY[16] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};

static const u1_t PROGMEM APPSKEY[16] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};
/* -------------------------------------------------- */

static osjob_t sendjob;
char dispositivo[16];       // preenchido no setup com o DevAddr, p/ mostrar no OLED
unsigned int counter = 0;

// Mapeamento dos pinos do ESP32LoRa
const lmic_pinmap lmic_pins = {
    .nss = 18,
    .rxtx = LMIC_UNUSED_PIN,
    .rst = 14,
    //.dio = {26, 33, 32}  // Heltec ESP32 Lora com antena metálica V1
    .dio = {26, 34, 35},  // Heltec ESP32 Lora com antena metálica V2 ou Wireless Stick
    .rxtx_rx_active = 0,
    .rssi_cal = 10,
    .spi_freq = 8000000
};

void printHex2(unsigned v) {
    v &= 0xff;
    if (v < 16)
        Serial.print('0');
    Serial.print(v, HEX);
}

void onEvent (ev_t ev) {
    Serial.print(os_getTime());
    Serial.print(": ");
    switch(ev) {
        case EV_SCAN_TIMEOUT:
            Serial.println(F("EV_SCAN_TIMEOUT"));
            break;
        case EV_BEACON_FOUND:
            Serial.println(F("EV_BEACON_FOUND"));
            break;
        case EV_BEACON_MISSED:
            Serial.println(F("EV_BEACON_MISSED"));
            break;
        case EV_BEACON_TRACKED:
            Serial.println(F("EV_BEACON_TRACKED"));
            break;
        case EV_JOINING:
            Serial.println(F("EV_JOINING"));
            display.clear();
            display.drawString(0, 16, "OTAA joining....");
            display.display();
            break;
        case EV_JOINED:
            Serial.println(F("EV_JOINED"));
            display.clear();
            display.drawString(0, 0, "Joined!");
            display.display();
            {
              u4_t netid = 0;
              devaddr_t devaddr = 0;
              u1_t nwkKey[16];
              u1_t artKey[16];
              LMIC_getSessionKeys(&netid, &devaddr, nwkKey, artKey);
              Serial.print("netid: ");
              Serial.println(netid, DEC);
              Serial.print("devaddr: ");
              Serial.println(devaddr, HEX);
              Serial.print("AppSKey: ");
              for (size_t i=0; i<sizeof(artKey); ++i) {
                if (i != 0)
                  Serial.print("-");
                printHex2(artKey[i]);
              }
              Serial.println("");
              Serial.print("NwkSKey: ");
              for (size_t i=0; i<sizeof(nwkKey); ++i) {
                if (i != 0)
                  Serial.print("-");
                  printHex2(nwkKey[i]);
              }
              Serial.println();
            }

            LMIC_setLinkCheckMode(0);
            break;

        case EV_JOIN_FAILED:
            Serial.println(F("EV_JOIN_FAILED"));
            display.clear();
            display.drawString (0, 0, "EV_JOIN_FAILED event!");
            display.display ();
            break;
        case EV_REJOIN_FAILED:
            Serial.println(F("EV_REJOIN_FAILED"));
            break;
        case EV_TXCOMPLETE:
            Serial.println(F("EV_TXCOMPLETE (includes waiting for RX windows)"));
            display.clear();
            display.drawString (0, 0, "EV_TXCOMPLETE event!");
            display.drawString (0, 25, dispositivo);
            display.display ();
            if (LMIC.txrxFlags & TXRX_ACK)
              Serial.println(F("Received ack"));
            if (LMIC.dataLen) {
              Serial.print(F("Received "));
              Serial.print(LMIC.dataLen);
              Serial.println(F(" bytes of payload"));
            }

        // Controle do LED via Downlink
        if( ( LMIC.txrxFlags & ( TXRX_DNW1 | TXRX_DNW2 ) ) != 0 ) {
          Serial.println( "Received downlink: ");
          if( LMIC.dataLen) {
            int teste = ( LMIC.frame[LMIC.dataBeg] << 8 ); // coleta o payload (codificado em bytes)
            Serial.println( teste );
            if ( teste == 256){           // payload: 0x01
              digitalWrite(LEDPIN, HIGH);}
            else {                        // payload: qualquer outro valor
              digitalWrite(LEDPIN, LOW);}

          }
          Serial.println();
        }

        if (LMIC.txrxFlags & TXRX_ACK) {
          Serial.println(F("Received ack"));
          display.drawString (0, 20, "Received ACK.");
          display.display ();
        }

        if (LMIC.dataLen) {
          int i = 0;
          // data received in rx slot after tx
          Serial.print(F("Data Received: "));
          Serial.write(LMIC.frame + LMIC.dataBeg, LMIC.dataLen);
          Serial.println();
          Serial.println(LMIC.rssi);

          display.drawString (0, 9, "Downlink Received!");
          for ( i = 0 ; i < LMIC.dataLen ; i++ )
            TTN_response[i] = LMIC.frame[LMIC.dataBeg+i];
          TTN_response[i] = 0;
        }
            // fim do trecho - downlink

            // Agenda a próxima transmissão
            os_setTimedCallback(&sendjob, os_getTime()+sec2osticks(TX_INTERVAL), do_send);

            display.drawString (0, 50, String (counter - 1));
            display.display ();
            break;
        case EV_LOST_TSYNC:
            Serial.println(F("EV_LOST_TSYNC"));
            break;
        case EV_RESET:
            Serial.println(F("EV_RESET"));
            break;
        case EV_RXCOMPLETE:
            // data received in ping slot
            Serial.println(F("EV_RXCOMPLETE"));
            break;
        case EV_LINK_DEAD:
            Serial.println(F("EV_LINK_DEAD"));
            break;
        case EV_LINK_ALIVE:
            Serial.println(F("EV_LINK_ALIVE"));
            break;

        case EV_TXSTART:
            Serial.println(F("EV_TXSTART"));
            break;
        case EV_TXCANCELED:
            Serial.println(F("EV_TXCANCELED"));
            break;
        case EV_RXSTART:
            /* do not print anything -- it wrecks timing */
            break;
        case EV_JOIN_TXCOMPLETE:
            Serial.println(F("EV_JOIN_TXCOMPLETE: no JoinAccept"));

            display.clear();
            display.drawString (0, 16, "No JoinAccept!");
            display.drawString (0, 24, "Retrying...");
            display.display();
            break;

        default:
            Serial.print(F("Unknown event: "));
            Serial.println((unsigned) ev);
            break;
    }
}

/* Abre o BME280 e configura a amostragem.
 *
 * Precisa ser uma função só porque begin() REDEFINE a amostragem para o padrão
 * da biblioteca (modo contínuo). Chamar begin() sem reaplicar setSampling()
 * devolveria o sensor ao auto-aquecimento sem nenhum sinal visível. */
bool iniciarBME() {
    if (!bme.begin(BME_ADDR, &Wire1) && !bme.begin(0x77, &Wire1)) return false;

    /* Modo forçado: o sensor dorme e só acorda quando pedimos. No modo
     * contínuo ele se auto-aquece e passa a ler ~1 °C a mais que o ambiente —
     * erro fatal para detectar geada.
     *
     * Filtro IIR desligado: ele serve para suavizar rajadas em leitura
     * contínua; amostrando uma vez por minuto só atrasaria a resposta a uma
     * mudança real de temperatura. */
    bme.setSampling(Adafruit_BME280::MODE_FORCED,
                    Adafruit_BME280::SAMPLING_X1,   // temperatura
                    Adafruit_BME280::SAMPLING_X1,   // pressão
                    Adafruit_BME280::SAMPLING_X1,   // umidade
                    Adafruit_BME280::FILTER_OFF);
    return true;
}

/* Lê o BME280 e monta o JSON do uplink.
 *
 * As chaves são de uma letra ("t", "h", "p") de propósito. O hub aceita tanto
 * o nome completo quanto a abreviação (veja _grandezas em src/hub/coletor.py),
 * e o tamanho importa: se o enlace cair para DR0 o limite do AU915 é 51 bytes,
 * e {"temperature":22.4,"humidity":58.1,"pressure":1009.5} tem 54 — não caberia.
 * Com as abreviações fica {"t":22.4,"h":58.1,"p":1009.5}, 30 bytes, que passa
 * em qualquer taxa de dados.
 *
 * Valores arredondados a 1 casa: o BME280 não tem exatidão melhor que isso
 * (±0,5 °C, ±3 % UR) e cada dígito a mais é um byte a mais no ar. */
void montarPayload() {
    doc.clear();

    if (!bme_ok) {
        // Nova tentativa: o módulo pode ter sido religado ou o cabo reencaixado.
        bme_ok = iniciarBME();
    }

    if (bme_ok) {
        bme.takeForcedMeasurement();   // acorda, mede uma vez, volta a dormir
        float t = bme.readTemperature();          // °C
        float h = bme.readHumidity();             // % UR
        float p = bme.readPressure() / 100.0F;    // Pa → hPa

        if (isnan(t) || isnan(h) || isnan(p)) {   // leitura inválida: I2C caiu
            bme_ok = false;
        } else {
            doc["t"] = round(t * 10) / 10.0;
            doc["h"] = round(h * 10) / 10.0;
            doc["p"] = round(p * 10) / 10.0;
        }
    }

    if (!bme_ok) {
        /* Sem sensor, ainda assim transmitimos. O hub vai recusar a leitura
         * ("sem grandezas reconhecidas"), mas o pacote aparece no ChirpStack e
         * no `hub espiar` — é como se distingue "sensor quebrado" de "nó fora
         * do alcance do gateway", que no silêncio total seriam idênticos. */
        doc["err"] = "bme280";
    }
}

void do_send(osjob_t* j){     //Função de envio de dados

    // Verificar se não há outra transmissão em andamento
    if (LMIC.opmode & OP_TXRXPEND) {
        Serial.println(F("OP_TXRXPEND, not sending"));
    } else {
        // Preparação dos dados para envio (payload)
        montarPayload();

        // Criar o payload Json
        int nDados = serializeJson(doc, payload);
        Serial.print("Data to send: ");
        serializeJson(doc, Serial);
        Serial.printf("  (%d bytes)\n", nDados);

        /* Preparação dos dados:
        Primeiro parâmetro: canal (1 a 233)
        Segundo parâmetro: byte(s) de dados
        Terceiro parâmetro: tamanho do pacote de dados
        Quarto parâmetro: solicitação de confirmação (acknowledge)

        O quarto parâmetro é 0 (NÃO confirmado) de propósito. Com 1, o nó espera
        um ACK — que é um downlink, justamente o ponto fraco de um gateway de
        canal único. Sem receber ACK ele retransmite o mesmo quadro várias vezes
        (o servidor descarta como UPLINK_F_CNT_RETRANSMISSION) e ainda degrada o
        spreading factor a cada tentativa, de DR5 até DR2.

        Para monitoramento climático, perder um pacote ocasional é irrelevante
        perto do custo de retransmitir: cada tentativa gasta tempo de ar e
        bateria. */
        LMIC_setTxData2(1, payload, nDados, 0);
        Serial.println(F("Packet queued"));

        display.clear();
        display.drawString (0, 0, "Enviando uplink...");
        if (bme_ok) {
          display.drawString (0, 14, String(doc["t"].as<float>(), 1) + " C   "
                                   + String(doc["h"].as<float>(), 1) + " %");
          display.drawString (0, 26, String(doc["p"].as<float>(), 1) + " hPa");
        } else {
          display.drawString (0, 14, "BME280 nao encontrado");
          display.drawString (0, 26, "SDA=21 SCL=22 addr 0x76");
        }
        display.drawString (0, 40, dispositivo);
        display.drawString (0, 50, "pkt " + String (++counter));
        display.display ();
    }
    // A próxima transmissão é agendada após o evento TX_COMPLETE.
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println(F("Starting..."));
    pinMode(LEDPIN,OUTPUT);

    //Inicialização do display OLED
    pinMode(OLED_RESET, OUTPUT);
    digitalWrite(OLED_RESET, LOW);
    delay(50);
    digitalWrite(OLED_RESET, HIGH);

    display.init ();
    display.setFont (ArialMT_Plain_10);
    display.setTextAlignment (TEXT_ALIGN_LEFT);
    display.drawString (0, 16, "Starting....");
    display.display ();
    delay(500);

    #ifdef VCC_ENABLE
    pinMode(VCC_ENABLE, OUTPUT);
    digitalWrite(VCC_ENABLE, HIGH);
    delay(1000);
    #endif

    // Inicialização do BME280 no segundo barramento I2C
    Wire1.begin(BME_SDA, BME_SCL);
    bme_ok = iniciarBME();
    if (bme_ok) {
        Serial.println(F("BME280 encontrado"));
    } else {
        Serial.println(F("BME280 NAO encontrado - confira SDA=21 SCL=22, 3V3 e o endereco (0x76/0x77)"));
    }
    display.drawString(0, 30, bme_ok ? "BME280 ok" : "BME280 ausente");
    display.display();

    os_init();      // Inicialização da biblioteca LMIC
    LMIC_reset();   // Descarta dados pendentes de transmissão
    LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100); //aumenta a tolerância a erro de clock

    /* Ativação da sessão LoRaWAN.
     * Em ABP a sessão já nasce pronta — não há join, e portanto não dependemos
     * do downlink JoinAccept, que é o ponto fraco de um gateway de canal único.
     * Em OTAA, o join acontece na primeira transmissão (do_send abaixo). */
    #if _USAR_ABP == 1
      {
        uint8_t nwkskey[sizeof(NWKSKEY)];
        uint8_t appskey[sizeof(APPSKEY)];
        memcpy_P(nwkskey, NWKSKEY, sizeof(NWKSKEY));
        memcpy_P(appskey, APPSKEY, sizeof(APPSKEY));
        LMIC_setSession(0x13, DEVADDR, nwkskey, appskey);
      }
      snprintf(dispositivo, sizeof(dispositivo), "%08X", (unsigned)DEVADDR);
      Serial.println(F("Modo ABP: sessao pre-configurada, sem join"));
    #else
      snprintf(dispositivo, sizeof(dispositivo), "OTAA");
    #endif

    // Configurações da banda de transmissão
    #if defined(CFG_au915)
      LMIC_selectSubBand(1);
      /* Seleção de canais:
       * (0) = canais 0 a 7 (Everynet-ATC)
       * (1) = canais 8 a 15 (TTN) -- tambem a sub-banda do nosso gateway
       * (2) = canais 16 a 23 etc... */

      /* GATEWAY DE CANAL UNICO: a sub-banda acima habilita 8 canais e o LMIC
       * salta entre eles a cada transmissao. Nosso gateway na TV Box escuta
       * UMA unica frequencia (916.8 MHz = canal 8), entao 7 de cada 8 uplinks
       * seriam perdidos. Fixamos o no no canal 8. */
      for (int canal = 0; canal < 72; canal++) {
        if (canal != _CANAL_UNICO) LMIC_disableChannel(canal);
      }
    #endif

    /* ADR desligado. O parametro 1 LIGA o ADR (o comentario original estava
     * invertido). Com gateway de canal unico o ADR e nocivo: o servidor tenta
     * remanejar canais e taxa de dados, e o enlace cai. */
    LMIC_setAdrMode(0);
    LMIC_setLinkCheckMode(0);   // desabilita a verificação de validação do link (evita erros)
    LMIC.dn2Dr = _SF_TRABALHO;  // RX2 no mesmo SF do uplink (gateway 1ch responde assim)
    LMIC_setDrTxpow(_SF_TRABALHO, 14); // taxa de dados e potência da transmissão

    do_send(&sendjob);          // Inicia a tarefa de transmissão (inclusive autenticação)
}

void loop() {
    os_runloop_once();
}
