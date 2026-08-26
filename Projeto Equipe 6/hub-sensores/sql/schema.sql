-- Esquema do hub de sensores.
-- Ideia central: o backhaul e intermitente (Wi-Fi/4G em campo, ou LoRa como
-- rota de emergencia), entao o banco decide o que sobe, em que ordem, e o que
-- fica. As flags `enviado` sao a fila de saida; enquanto a comunicacao estiver
-- fora do ar os registros se acumulam sem perda.
--
-- As leituras chegam de duas origens que convergem no MQTT: sensores Zigbee
-- (via Zigbee2MQTT) e nos LoRaWAN (via gateway local). O esquema e o mesmo para
-- ambas; o que muda e a cadencia de reporte, calibrada em `janela_s`.

PRAGMA journal_mode = WAL;      -- persistente: reduz escrita no cartao SD
PRAGMA foreign_keys = ON;

-- Metadados dos sensores Zigbee conhecidos.
CREATE TABLE IF NOT EXISTS sensores (
    id        INTEGER PRIMARY KEY,
    ieee      TEXT    NOT NULL UNIQUE,   -- 0xa4c138807355ffff ou nome amigavel do Z2M
    nome      TEXT,                      -- estufa_norte
    modelo    TEXT,                      -- TS0201
    local     TEXT,
    criado_em INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Serie temporal bruta. Fica so na box; nunca sobe pelo LoRa.
CREATE TABLE IF NOT EXISTS leituras (
    id          INTEGER PRIMARY KEY,
    sensor_id   INTEGER NOT NULL REFERENCES sensores(id) ON DELETE CASCADE,
    ts          INTEGER NOT NULL,        -- epoch UTC
    temperatura REAL,
    umidade     REAL,
    bateria     INTEGER,
    linkquality INTEGER
);
CREATE INDEX IF NOT EXISTS ix_leituras_sensor_ts ON leituras(sensor_id, ts);
CREATE INDEX IF NOT EXISTS ix_leituras_ts        ON leituras(ts);

-- Resumos por janela (padrao: 1 hora). E ISTO que o LoRa transporta.
-- Guardar min/max e essencial: uma geada de 20 min some numa media horaria.
CREATE TABLE IF NOT EXISTS agregados (
    id         INTEGER PRIMARY KEY,
    sensor_id  INTEGER NOT NULL REFERENCES sensores(id) ON DELETE CASCADE,
    inicio     INTEGER NOT NULL,         -- epoch do inicio da janela
    temp_min   REAL,
    temp_max   REAL,
    temp_media REAL,
    umid_min   REAL,
    umid_max   REAL,
    umid_media REAL,
    bateria    INTEGER,
    amostras   INTEGER NOT NULL,
    enviado    INTEGER NOT NULL DEFAULT 0,
    enviado_em INTEGER,
    UNIQUE(sensor_id, inicio)
);
-- Indice parcial: contem apenas a fila pendente, entao encolhe conforme sobe.
CREATE INDEX IF NOT EXISTS ix_agregados_pendentes
    ON agregados(inicio) WHERE enviado = 0;

-- Resultado do processamento de borda. Sobe na frente dos agregados.
CREATE TABLE IF NOT EXISTS eventos (
    id         INTEGER PRIMARY KEY,
    sensor_id  INTEGER REFERENCES sensores(id) ON DELETE CASCADE,
    ts         INTEGER NOT NULL,
    tipo       TEXT    NOT NULL,         -- geada, calor_extremo, umidade_baixa, sensor_mudo, bateria_baixa
    valor      REAL,
    detalhe    TEXT,
    prioridade INTEGER NOT NULL DEFAULT 1,   -- maior = mais urgente
    enviado    INTEGER NOT NULL DEFAULT 0,
    enviado_em INTEGER
);
CREATE INDEX IF NOT EXISTS ix_eventos_pendentes
    ON eventos(prioridade DESC, ts) WHERE enviado = 0;
CREATE INDEX IF NOT EXISTS ix_eventos_sensor_tipo ON eventos(sensor_id, tipo, ts);

-- Chave/valor para estado interno (ultima agregacao, versao do esquema...).
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

-- Visao de conveniencia para inspecao manual.
CREATE VIEW IF NOT EXISTS v_ultimas_leituras AS
SELECT s.ieee,
       COALESCE(s.nome, s.ieee) AS sensor,
       datetime(l.ts, 'unixepoch', 'localtime') AS quando,
       l.temperatura, l.umidade, l.bateria, l.linkquality
FROM leituras l
JOIN sensores s ON s.id = l.sensor_id
ORDER BY l.ts DESC;
