-- Estrutura do banco do SecBox (PostgreSQL)
-- Requer a extensão pgcrypto (bcrypt + geração de tokens):
--   CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Usuários do app (donos das contas)
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,        -- bcrypt (via crypt()/gen_salt('bf'))
    name          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- O UNIQUE acima distingue maiúsculas, então 'Ana@x.com' e 'ana@x.com' passariam
-- como contas diferentes. Este índice impede o cadastro duplicado.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (lower(email));

-- Dispositivos (TV box)
CREATE TABLE devices (
    id          BIGSERIAL PRIMARY KEY,
    device_id   TEXT UNIQUE NOT NULL,     -- ex: TVB-7F3A91 (vai no QR)
    secret_hash TEXT NOT NULL,            -- segredo de fábrica (hash)
    owner_id    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    name        TEXT,
    model       TEXT,
    claimed_at  TIMESTAMPTZ,             -- quando foi pareado
    last_seen   TIMESTAMPTZ,             -- último contato
    online      BOOLEAN DEFAULT false,   -- presença (status/heartbeat)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Eventos / telemetria vindos dos módulos
CREATE TABLE events (
    id         BIGSERIAL PRIMARY KEY,
    device_id  TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    module     TEXT NOT NULL,            -- camera | alarme | acesso
    type       TEXT NOT NULL,            -- ex: motion, snapshot_taken
    payload    JSONB,                    -- dados livres do evento
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_device_time ON events (device_id, created_at DESC);

-- Sessões do app (token de login)
CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '30 days'
);

-- Tokens temporários de pareamento (claiming)
CREATE TABLE claim_tokens (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ
);

-- Tokens FCM dos celulares (push)
CREATE TABLE push_tokens (
    fcm_token  TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
