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

-- Marca se o dono provou controlar a caixa de e-mail. Contas antigas ficam
-- como não verificadas; o app avisa, mas o login continua funcionando.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false;

-- Códigos de 6 dígitos enviados por e-mail (confirmação e recuperação de senha).
-- Código, e não link: o servidor só é alcançável pela Tailscale, então um link
-- no e-mail abriria no navegador do celular e não chegaria a lugar nenhum.
CREATE TABLE IF NOT EXISTS email_codes (
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose    TEXT   NOT NULL,          -- 'verify' | 'reset'
    code_hash  TEXT   NOT NULL,          -- bcrypt: o código nunca fica em claro
    attempts   INT    NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, purpose)       -- um código ativo por finalidade
);
