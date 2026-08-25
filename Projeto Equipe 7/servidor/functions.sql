-- Funções do SecBox (PostgreSQL / plpgsql)

-- O PostgreSQL nao aceita CREATE OR REPLACE quando o tipo de retorno muda, e o
-- login() ganhou a coluna email_verified. Sem este DROP, reaplicar o arquivo
-- numa base ja instalada aborta aqui e nada abaixo e criado.
-- Rode o arquivo com "psql -1" para que o drop e o create sejam atomicos: sem
-- isso existe uma janela, ainda que curta, em que ninguem consegue entrar.
DROP FUNCTION IF EXISTS login(TEXT, TEXT);

-- login: valida a senha (bcrypt) e emite um token de sessão.
-- O e-mail é comparado sem diferenciar maiúsculas: o cadastro grava em minúsculas
-- e ninguém deveria ficar de fora da conta por ter digitado "Fulano@..." .
CREATE OR REPLACE FUNCTION login(p_email TEXT, p_password TEXT)
RETURNS TABLE(token TEXT, user_id BIGINT, name TEXT, email_verified BOOLEAN) AS $$
DECLARE v_id BIGINT; v_name TEXT; v_token TEXT; v_ver BOOLEAN;
BEGIN
    SELECT u.id, u.name, u.email_verified INTO v_id, v_name, v_ver FROM users u
        WHERE lower(u.email) = lower(btrim(p_email))
          AND u.password_hash = crypt(p_password, u.password_hash);
    IF v_id IS NULL THEN RETURN; END IF;
    v_token := encode(gen_random_bytes(24), 'hex');
    INSERT INTO sessions(token, user_id) VALUES (v_token, v_id);
    -- O app usa email_verified para insistir na confirmacao sem bloquear o
    -- acesso: barrar o login de quem nao confirmou puniria contas antigas.
    RETURN QUERY SELECT v_token, v_id, v_name, v_ver;
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

-- set_push: liga ou desliga as notificações deste aparelho para a conta da
-- sessão. Dois cuidados que evitam alerta indo para quem não devia:
--   * ON CONFLICT: se outra pessoa entrar no mesmo celular, o token muda de
--     dono em vez de continuar entregando os alertas da conta anterior;
--   * remoção no logout: sem isso o aparelho segue recebendo depois de sair.
CREATE OR REPLACE FUNCTION set_push(p_session TEXT, p_fcm TEXT, p_remove BOOLEAN)
RETURNS TEXT AS $$
DECLARE v_user BIGINT;
BEGIN
    v_user := user_from_token(p_session);
    IF v_user IS NULL THEN RETURN 'unauthorized'; END IF;
    IF p_remove THEN
        DELETE FROM push_tokens WHERE fcm_token = p_fcm AND user_id = v_user;
    ELSE
        INSERT INTO push_tokens(fcm_token, user_id) VALUES (p_fcm, v_user)
        ON CONFLICT (fcm_token) DO UPDATE SET user_id = EXCLUDED.user_id;
    END IF;
    RETURN 'ok';
END; $$ LANGUAGE plpgsql;

-- claim_device: valida o token de pareamento E o segredo de fábrica, e vincula
-- o aparelho ao dono.
--
-- A validação do segredo não é detalhe: sem ela, qualquer pessoa com uma conta
-- (que gera token de pareamento à vontade) reivindica qualquer aparelho cujo
-- device_id ela conheça. Atrás da Tailscale isso era teórico; publicado na
-- internet é "roube a câmera do vizinho sabendo o ID dela".
CREATE OR REPLACE FUNCTION claim_device(p_device_id TEXT, p_secret TEXT, p_token TEXT)
RETURNS TEXT AS $$
DECLARE v_user BIGINT; v_hash TEXT;
BEGIN
    SELECT user_id INTO v_user FROM claim_tokens
        WHERE token = p_token AND used_at IS NULL AND expires_at > now();
    IF v_user IS NULL THEN RETURN 'invalid_token'; END IF;

    SELECT secret_hash INTO v_hash FROM devices WHERE device_id = p_device_id;
    IF v_hash IS NULL THEN RETURN 'unknown_device'; END IF;

    -- secret_hash que não é bcrypt é resquício de cadastro manual (o piloto
    -- gravou o literal 'pendente-hash'). Recusar com erro próprio, em vez de
    -- deixar passar: falha explícita e corrigível é melhor que buraco silencioso.
    IF left(v_hash, 2) <> '$2' THEN RETURN 'device_not_provisioned'; END IF;
    IF v_hash <> crypt(coalesce(p_secret, ''), v_hash) THEN
        RETURN 'invalid_secret';
    END IF;

    UPDATE devices SET owner_id = v_user, claimed_at = now()
        WHERE device_id = p_device_id;
    UPDATE claim_tokens SET used_at = now() WHERE token = p_token;
    RETURN 'ok';
END; $$ LANGUAGE plpgsql;

-- Exemplo de criação de usuário (senha com hash bcrypt):
-- INSERT INTO users (email, password_hash, name)
--   VALUES ('voce@exemplo.com', crypt('SUA_SENHA', gen_salt('bf')), 'Seu Nome');

-- ---------------------------------------------------------------------------
-- Verificação de e-mail e recuperação de senha
--
-- Sem e-mail confirmado a conta é perdível: esquecida a senha, não há caminho
-- de volta, e o dispositivo fica preso a um dono que não consegue mais entrar.
-- ---------------------------------------------------------------------------

-- request_email_code: gera o código de 6 dígitos e devolve em claro para quem
-- vai enviá-lo (o Node-RED, do lado do servidor). No banco fica só o hash.
--
-- Devolve sempre 'ok' quando o e-mail não existe: quem pede recuperação não
-- pode descobrir, pela resposta, se um endereço tem conta.
CREATE OR REPLACE FUNCTION request_email_code(p_email TEXT, p_purpose TEXT)
RETURNS TABLE(status TEXT, code TEXT, name TEXT) AS $$
DECLARE v_id BIGINT; v_name TEXT; v_code TEXT; v_recente TIMESTAMPTZ;
BEGIN
    IF p_purpose NOT IN ('verify', 'reset') THEN
        RETURN QUERY SELECT 'invalid_purpose', NULL::TEXT, NULL::TEXT; RETURN;
    END IF;

    SELECT u.id, u.name INTO v_id, v_name FROM users u
        WHERE lower(u.email) = lower(btrim(p_email));
    IF v_id IS NULL THEN
        RETURN QUERY SELECT 'ok', NULL::TEXT, NULL::TEXT; RETURN;
    END IF;

    -- Um pedido por minuto: sem isto, o endpoint vira gerador de spam para
    -- terceiros, e é o e-mail do servidor que paga a reputação.
    SELECT created_at INTO v_recente FROM email_codes
        WHERE user_id = v_id AND purpose = p_purpose;
    IF v_recente IS NOT NULL AND v_recente > now() - interval '1 minute' THEN
        RETURN QUERY SELECT 'too_soon', NULL::TEXT, NULL::TEXT; RETURN;
    END IF;

    v_code := lpad((floor(random() * 1000000))::INT::TEXT, 6, '0');
    INSERT INTO email_codes(user_id, purpose, code_hash, expires_at)
         VALUES (v_id, p_purpose, crypt(v_code, gen_salt('bf')),
                 now() + interval '15 minutes')
    ON CONFLICT (user_id, purpose) DO UPDATE
        SET code_hash = EXCLUDED.code_hash, expires_at = EXCLUDED.expires_at,
            created_at = now(), attempts = 0;

    RETURN QUERY SELECT 'ok', v_code, v_name;
END; $$ LANGUAGE plpgsql;

-- check_email_code: confere o código e o consome. Uso interno das duas funções
-- abaixo. Limita a 5 tentativas — 6 dígitos são 1 milhão de combinações, e sem
-- limite dá para varrer todas antes de expirar.
CREATE OR REPLACE FUNCTION check_email_code(p_user BIGINT, p_purpose TEXT, p_code TEXT)
RETURNS TEXT AS $$
DECLARE v_hash TEXT; v_exp TIMESTAMPTZ; v_try INT;
BEGIN
    SELECT code_hash, expires_at, attempts INTO v_hash, v_exp, v_try
        FROM email_codes WHERE user_id = p_user AND purpose = p_purpose;
    IF v_hash IS NULL THEN RETURN 'no_code'; END IF;
    IF v_exp < now() THEN
        DELETE FROM email_codes WHERE user_id = p_user AND purpose = p_purpose;
        RETURN 'expired';
    END IF;
    IF v_try >= 5 THEN
        DELETE FROM email_codes WHERE user_id = p_user AND purpose = p_purpose;
        RETURN 'too_many_attempts';
    END IF;
    IF v_hash <> crypt(coalesce(p_code, ''), v_hash) THEN
        UPDATE email_codes SET attempts = attempts + 1
            WHERE user_id = p_user AND purpose = p_purpose;
        RETURN 'invalid_code';
    END IF;
    DELETE FROM email_codes WHERE user_id = p_user AND purpose = p_purpose;
    RETURN 'ok';
END; $$ LANGUAGE plpgsql;

-- confirm_email: o usuário digita o código no app e o e-mail passa a valer.
CREATE OR REPLACE FUNCTION confirm_email(p_email TEXT, p_code TEXT)
RETURNS TEXT AS $$
DECLARE v_id BIGINT; v_r TEXT;
BEGIN
    SELECT id INTO v_id FROM users WHERE lower(email) = lower(btrim(p_email));
    IF v_id IS NULL THEN RETURN 'invalid_code'; END IF;  -- não revela a ausência
    v_r := check_email_code(v_id, 'verify', p_code);
    IF v_r <> 'ok' THEN RETURN v_r; END IF;
    UPDATE users SET email_verified = true WHERE id = v_id;
    RETURN 'ok';
END; $$ LANGUAGE plpgsql;

-- reset_password: troca a senha provando controle da caixa de e-mail.
--
-- Três efeitos além da troca, todos deliberados:
--   * apaga as sessões: se a conta foi tomada, o invasor perde o acesso agora,
--     e não daqui a 30 dias quando o token dele expirar;
--   * apaga os push_tokens: senão o aparelho do invasor segue recebendo os
--     alertas da casa de quem acabou de recuperar a conta;
--   * marca o e-mail como verificado, já que digitar o código prova isso.
CREATE OR REPLACE FUNCTION reset_password(p_email TEXT, p_code TEXT, p_new TEXT)
RETURNS TEXT AS $$
DECLARE v_id BIGINT; v_r TEXT;
BEGIN
    IF length(coalesce(p_new, '')) < 8 THEN RETURN 'weak_password'; END IF;
    SELECT id INTO v_id FROM users WHERE lower(email) = lower(btrim(p_email));
    IF v_id IS NULL THEN RETURN 'invalid_code'; END IF;
    v_r := check_email_code(v_id, 'reset', p_code);
    IF v_r <> 'ok' THEN RETURN v_r; END IF;

    UPDATE users SET password_hash = crypt(p_new, gen_salt('bf')),
                     email_verified = true
        WHERE id = v_id;
    DELETE FROM sessions    WHERE user_id = v_id;
    DELETE FROM push_tokens WHERE user_id = v_id;
    RETURN 'ok';
END; $$ LANGUAGE plpgsql;

-- user_account: quem é o dono desta sessão.
--
-- Existe por um motivo específico: o login() devolve email_verified, mas o app
-- guarda o token e nas aberturas seguintes não passa pelo login — e sem isto
-- quem já estava logado com e-mail não confirmado nunca ficaria sabendo, que é
-- justamente o caso das contas criadas antes desta funcionalidade.
--
-- (Nome deliberadamente explícito: "session_user" é palavra reservada no
-- PostgreSQL, e "user" sozinho também.)
CREATE OR REPLACE FUNCTION user_account(p_token TEXT)
RETURNS TABLE(user_id BIGINT, email TEXT, name TEXT, email_verified BOOLEAN) AS $$
    SELECT u.id, u.email, u.name, u.email_verified
      FROM sessions s
      JOIN users u ON u.id = s.user_id
     WHERE s.token = p_token AND s.expires_at > now();
$$ LANGUAGE sql;

-- device_token: entrega o token de mídia da box, e só ao dono.
--
-- Sem esta rota o app não teria como falar com a box depois que a 9997 e o
-- MediaMTX passaram a exigir autenticação — e embutir o token no APK seria
-- publicá-lo, já que qualquer pessoa desmonta um APK.
CREATE OR REPLACE FUNCTION device_token(p_session TEXT, p_device_id TEXT)
RETURNS TEXT AS $$
    SELECT d.access_token
      FROM devices d
     WHERE d.device_id = p_device_id
       AND d.owner_id = user_from_token(p_session);
$$ LANGUAGE sql;

-- device_owned: a sessão é dona deste aparelho?
--
-- Guarda da rota /api/command. Sem ela, qualquer usuário autenticado mandaria
-- comando para o aparelho de qualquer outro — disparar a sirene, tirar
-- snapshot, alterar configuração de câmera.
CREATE OR REPLACE FUNCTION device_owned(p_session TEXT, p_device TEXT)
RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM devices d
         WHERE d.device_id = p_device
           AND d.owner_id = user_from_token(p_session)
    );
$$ LANGUAGE sql;
