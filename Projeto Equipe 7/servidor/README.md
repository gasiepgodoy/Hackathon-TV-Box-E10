# Servidor (Debian)

Stack: **Mosquitto** (broker MQTT) + **PostgreSQL** + **Node-RED** (API/regras) + **microserviço FCM**.

## Conteúdo

| Arquivo | Descrição |
|---|---|
| [`schema.sql`](schema.sql) | Estrutura do banco (tabelas). |
| [`functions.sql`](functions.sql) | Funções: `login`, `register_user`, `user_from_token`, `user_account`, `set_push`, `claim_device`, e as de e-mail. |
| [`mosquitto/default.conf`](mosquitto/default.conf) | Config do broker (auth por senha, sem TLS no piloto). |
| [`push-service/`](push-service/) | Microserviço Node.js de saída: push (FCM) e e-mail (SMTP). |

## Instalação (resumo)

```bash
# PostgreSQL
sudo apt install -y postgresql
sudo -u postgres psql -c "CREATE USER secadmin WITH PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE secdb OWNER secadmin;"
sudo -u postgres psql -d secdb -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql -h localhost -U secadmin -d secdb -f schema.sql
psql -h localhost -U secadmin -d secdb -1 -f functions.sql   # -1: tudo numa transacao

# Mosquitto
sudo apt install -y mosquitto mosquitto-clients
sudo mosquitto_passwd -c /etc/mosquitto/passwd serverapp
sudo cp mosquitto/default.conf /etc/mosquitto/conf.d/default.conf
sudo systemctl restart mosquitto

# Node-RED (32-bit: usar o nodejs do apt, não o script oficial)
sudo apt install -y nodejs npm
sudo npm install -g --unsafe-perm node-red@4
# instalar o nó node-red-contrib-postgresql pelo Manage Palette

# Saída: push (FCM) + e-mail (SMTP)
cd push-service && npm install
# colocar a chave do Firebase em push-service/secbox-sa.json
cp .env.example .env   # preencher as credenciais SMTP; carregar com
                       # EnvironmentFile no systemd do serviço
```

## Node-RED — regras e API

O Node-RED conecta ao broker (`localhost:1883`) e ao PostgreSQL (`secdb`), e expõe a
**API HTTP** do app na porta `1880`. As funções pesadas (auth, claim) ficam no
banco (`functions.sql`); os flows só fazem a cola.

### Flows (por tópico MQTT)
- **Eventos** — assina `devices/+/+/event` → grava na tabela `events`.
- **Presença** — assina `devices/+/status` e `devices/+/heartbeat` → atualiza `devices.online` / `last_seen`.
- **Provisionamento** — assina `provisioning/claim` → chama `claim_device(...)` → responde em `devices/{id}/provisioning/result`.
- **Alarme → Push** ([`nodered/alarme-push.json`](nodered/alarme-push.json)) — assina
  `devices/+/alarme/event` **e** `devices/+/camera/event` → busca os `push_tokens` do dono
  → monta o texto conforme o tipo do evento → chama o microserviço `localhost:3001/send`.
- **TV box caiu** ([`nodered/tvbox-offline.json`](nodered/tvbox-offline.json)) — assina `devices/+/status`;
  quando chega o *Last Will* (`online: false`) que o broker publica ao perder a TV box,
  republica como `alarme/event` do tipo `tvbox_offline`, reaproveitando o flow de push
  acima. Importar por **Menu → Import → Clipboard** e escolher o broker nos dois nós MQTT.

### Tipos de evento em `alarme/event`
| `type` | Origem | Significado |
|---|---|---|
| `movimento` | `motion.py` (borda) | Movimento na câmera indicada em `camera`/`name`. |
| `tvbox_offline` | Node-RED (via LWT) | A TV box saiu do ar (energia ou rede). |

| `camera_offline` | `agent.py` (borda) | A câmera indicada em `name` parou de responder. |
| `camera_online` | `agent.py` (borda) | A câmera voltou. |

> Os arquivos em [`nodered/`](nodered/) trazem **apenas os nós do flow** — os nós de
> configuração (broker e PostgreSQL) ficam de fora de propósito, para não sobrescrever
> as credenciais já instaladas. Ao importar, os nós se ligam sozinhos aos ids
> existentes (`mqtt_broker_local`, `pg_secdb`).

### API HTTP (porta 1880)
| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/register` | `{email, password, name}` → `{token, user_id, name}`; recusa com `409 email_taken`, `400 invalid_email` ou `400 weak_password`. Flow em [`nodered/api-cadastro.json`](nodered/api-cadastro.json). |
| POST | `/api/login` | `{email, password}` → `{token, user_id, name}` (via `login()`). |
| GET | `/api/devices` | Header `Authorization: Bearer <token>` → dispositivos do usuário. |
| POST | `/api/claim-token` | Gera um token de pareamento (expira em 15 min). |
| GET | `/api/events?device=<id>` | Histórico de eventos do dispositivo. |
| POST | `/api/register-push` | `{fcm_token}` → registra o token do celular (via `set_push()`). |
| POST | `/api/unregister-push` | `{fcm_token}` → para de notificar este aparelho (chamado ao sair da conta). Flow em [`nodered/api-push.json`](nodered/api-push.json). |
| POST | `/api/email/request-code` | `{email, purpose}` (`verify`\|`reset`) → envia código de 6 dígitos. **Responde sempre `200 {status:ok}`**, exista ou não a conta. Flow em [`nodered/api-email.json`](nodered/api-email.json). |
| POST | `/api/email/confirm` | `{email, code}` → marca o e-mail como verificado. |
| POST | `/api/password-reset` | `{email, code, password}` → troca a senha, encerra todas as sessões e remove os push tokens do usuário. |
| GET | `/api/me` | Header `Authorization: Bearer <token>` → `{user_id, email, name, email_verified}`; `401` se a sessão morreu. Flow em [`nodered/api-conta.json`](nodered/api-conta.json). |

> Nota de implementação: no nó `mqtt in` do Node-RED, o payload chega como Buffer;
> as funções fazem parse defensivo (`Buffer` → string → `JSON.parse`) antes de usar.

## Verificação de e-mail e recuperação de senha

Sem e-mail confirmado a conta é perdível: esquecida a senha não há caminho de
volta, e o dispositivo fica preso a um dono que não consegue mais entrar — que
foi exatamente o que aconteceu com uma das câmeras do piloto.

**Código de 6 dígitos, não link.** O servidor só é alcançável pela Tailscale;
um link no e-mail abriria no navegador do celular e não chegaria a lugar
nenhum. O app já fala com a API, então o código digitado usa o caminho que
existe e funciona.

Decisões que valem registro:

- **A resposta de `/api/email/request-code` é sempre a mesma**, exista ou não a
  conta, e inclusive quando o limite de um pedido por minuto barra o envio. Se
  as respostas diferissem, a rota viraria consulta pública de quem tem
  cadastro. Falha de SMTP também responde `200` — o erro fica no log do
  microserviço, que é onde alguém consegue agir sobre ele.
- **O código vive só como hash** (`bcrypt`) e expira em 15 minutos, com no
  máximo 5 tentativas. Seis dígitos são um milhão de combinações: sem limite,
  dá para varrer todas antes de expirar.
- **Redefinir a senha apaga as sessões e os push tokens do usuário.** Se a
  conta tinha sido tomada, quem estava dentro sai agora — e não daqui a 30 dias
  quando o token expirasse — e o aparelho do invasor para de receber os alertas
  da casa de quem acabou de recuperar a conta.
- **Existe `/api/me` porque o app guarda o token** e nas aberturas seguintes
  não passa pelo login. Sem essa rota, quem já estava logado com e-mail não
  confirmado nunca ficaria sabendo — que é o caso de todas as contas criadas
  antes desta mudança, inclusive a que segura a câmera do piloto. O app mostra
  um aviso na lista de dispositivos, com atalho para confirmar.
- **O login não é bloqueado para quem não confirmou.** Barrar puniria as contas
  criadas antes desta mudança; `login()` passou a devolver `email_verified`
  para o app insistir sem impedir.

> Ao aplicar o `functions.sql`, note que `login()` ganhou uma quarta coluna. O
> flow atual faz `SELECT token, user_id, name FROM login($1,$2)` e continua
> funcionando — para o app usar o aviso de e-mail não confirmado, basta
> acrescentar `email_verified` a esse SELECT.
>
> **Rode sempre com `psql -1`.** O PostgreSQL não aceita `CREATE OR REPLACE`
> quando o tipo de retorno muda, então o arquivo precisa dar `DROP FUNCTION` no
> `login()` antes de recriá-lo. Fora de uma transação isso abre uma janela em
> que ninguém consegue entrar — e, se algo falhar no meio, o banco fica sem a
> função de login.

## Pareamento: o segredo passou a ser validado

`claim_device` agora confere o segredo de fábrica contra `devices.secret_hash`,
além do token de pareamento. Sem isso, qualquer pessoa com uma conta — e
qualquer conta gera token de pareamento à vontade — reivindicaria qualquer
aparelho cujo `device_id` conhecesse. Atrás da Tailscale era risco teórico;
publicado na internet, não.

| Retorno | Significado |
|---|---|
| `ok` | vinculado |
| `invalid_token` | token de pareamento inexistente, usado ou expirado |
| `unknown_device` | `device_id` não está na tabela `devices` |
| `device_not_provisioned` | o `secret_hash` não é bcrypt (resquício de cadastro manual) |
| `invalid_secret` | o segredo não confere |

> **Atenção ao aplicar:** o piloto gravou o literal `pendente-hash` no
> `secret_hash` do `TVB-C90BB3`. Enquanto ele não for substituído por um hash de
> verdade, o pareamento desse aparelho responde `device_not_provisioned`. É
> falha proposital e explícita — melhor que continuar aceitando qualquer um.
> Para corrigir, com o segredo saindo da própria box e sem passar por terceiros:
>
> ```bash
> # na TV box
> jq -r .secret /opt/secbox/device.json
> # no servidor, colando o valor:
> psql -h localhost -U secadmin -d secdb -c >   "UPDATE devices SET secret_hash = crypt('COLE_AQUI', gen_salt('bf')) WHERE device_id='TVB-C90BB3'"
> ```
