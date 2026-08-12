-- Funções do SecBox (PostgreSQL / plpgsql)

-- login: valida a senha (bcrypt) e emite um token de sessão.
-- O e-mail é comparado sem diferenciar maiúsculas: o cadastro grava em minúsculas
-- e ninguém deveria ficar de fora da conta por ter digitado "Fulano@..." .
CREATE OR REPLACE FUNCTION login(p_email TEXT, p_password TEXT)
RETURNS TABLE(token TEXT, user_id BIGINT, name TEXT) AS $$
DECLARE v_id BIGINT; v_name TEXT; v_token TEXT;
BEGIN
    SELECT u.id, u.name INTO v_id, v_name FROM users u
        WHERE lower(u.email) = lower(btrim(p_email))
          AND u.password_hash = crypt(p_password, u.password_hash);
    IF v_id IS NULL THEN RETURN; END IF;
    v_token := encode(gen_random_bytes(24), 'hex');
    INSERT INTO sessions(token, user_id) VALUES (v_token, v_id);
    RETURN QUERY SELECT v_token, v_id, v_name;
END; $$ LANGUAGE plpgsql;

-- register_user: cria a conta e já devolve uma sessão, para o app entrar direto
-- em vez de pedir a senha de novo. Recusas voltam em "error" (e não como exceção),
-- para a API poder traduzir cada caso numa mensagem clara.
CREATE OR REPLACE FUNCTION register_user(p_email TEXT, p_password TEXT, p_name TEXT)
RETURNS TABLE(token TEXT, user_id BIGINT, name TEXT, error TEXT) AS $$
DECLARE v_id BIGINT; v_token TEXT; v_email TEXT; v_name TEXT;
BEGIN
    v_email := lower(btrim(coalesce(p_email, '')));
    v_name  := NULLIF(btrim(coalesce(p_name, '')), '');

    IF v_email !~ '^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$' THEN
        RETURN QUERY SELECT NULL::TEXT, NULL::BIGINT, NULL::TEXT, 'invalid_email';
        RETURN;
    END IF;
    IF length(coalesce(p_password, '')) < 8 THEN
        RETURN QUERY SELECT NULL::TEXT, NULL::BIGINT, NULL::TEXT, 'weak_password';
        RETURN;
    END IF;

    BEGIN
        INSERT INTO users(email, password_hash, name)
             VALUES (v_email, crypt(p_password, gen_salt('bf')), v_name)
          RETURNING id INTO v_id;
    EXCEPTION WHEN unique_violation THEN
        RETURN QUERY SELECT NULL::TEXT, NULL::BIGINT, NULL::TEXT, 'email_taken';
        RETURN;
    END;

    v_token := encode(gen_random_bytes(24), 'hex');
    INSERT INTO sessions(token, user_id) VALUES (v_token, v_id);
    RETURN QUERY SELECT v_token, v_id, v_name, NULL::TEXT;
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
