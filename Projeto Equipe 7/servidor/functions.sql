-- Funções do SecBox (PostgreSQL / plpgsql)

-- login: valida a senha (bcrypt) e emite um token de sessão
CREATE OR REPLACE FUNCTION login(p_email TEXT, p_password TEXT)
RETURNS TABLE(token TEXT, user_id BIGINT, name TEXT) AS $$
DECLARE v_id BIGINT; v_name TEXT; v_token TEXT;
BEGIN
    SELECT u.id, u.name INTO v_id, v_name FROM users u
        WHERE u.email = p_email
          AND u.password_hash = crypt(p_password, u.password_hash);
    IF v_id IS NULL THEN RETURN; END IF;
    v_token := encode(gen_random_bytes(24), 'hex');
    INSERT INTO sessions(token, user_id) VALUES (v_token, v_id);
    RETURN QUERY SELECT v_token, v_id, v_name;
END; $$ LANGUAGE plpgsql;

-- resolve um token de sessão para o user_id (autoriza as chamadas da API)
-- Obs.: NÃO usar o nome "session_user" — é palavra reservada no PostgreSQL.
CREATE OR REPLACE FUNCTION user_from_token(p_token TEXT)
RETURNS BIGINT AS $$
    SELECT user_id FROM sessions WHERE token = p_token AND expires_at > now();
$$ LANGUAGE sql;

-- claim_device: valida o token de pareamento e vincula o aparelho ao dono
CREATE OR REPLACE FUNCTION claim_device(p_device_id TEXT, p_secret TEXT, p_token TEXT)
RETURNS TEXT AS $$
DECLARE v_user BIGINT;
BEGIN
    SELECT user_id INTO v_user FROM claim_tokens
        WHERE token = p_token AND used_at IS NULL AND expires_at > now();
    IF v_user IS NULL THEN RETURN 'invalid_token'; END IF;

    -- (validação do secret via hash pode entrar aqui)
    UPDATE devices SET owner_id = v_user, claimed_at = now()
        WHERE device_id = p_device_id;
    IF NOT FOUND THEN RETURN 'unknown_device'; END IF;

    UPDATE claim_tokens SET used_at = now() WHERE token = p_token;
    RETURN 'ok';
END; $$ LANGUAGE plpgsql;

-- Exemplo de criação de usuário (senha com hash bcrypt):
-- INSERT INTO users (email, password_hash, name)
--   VALUES ('voce@exemplo.com', crypt('SUA_SENHA', gen_salt('bf')), 'Seu Nome');
