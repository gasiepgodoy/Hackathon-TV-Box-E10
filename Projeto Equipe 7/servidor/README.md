# Servidor (Debian)

Stack: **Mosquitto** (broker MQTT) + **PostgreSQL** + **Node-RED** (API/regras) + **microserviço FCM**.

## Conteúdo

| Arquivo | Descrição |
|---|---|
| [`schema.sql`](schema.sql) | Estrutura do banco (tabelas). |
| [`functions.sql`](functions.sql) | Funções: `login`, `user_from_token`, `claim_device`. |
| [`mosquitto/default.conf`](mosquitto/default.conf) | Config do broker (auth por senha, sem TLS no piloto). |
| [`push-service/`](push-service/) | Microserviço Node.js que envia os push (FCM). |

## Instalação (resumo)

```bash
# PostgreSQL
sudo apt install -y postgresql
sudo -u postgres psql -c "CREATE USER secadmin WITH PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE secdb OWNER secadmin;"
sudo -u postgres psql -d secdb -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql -h localhost -U secadmin -d secdb -f schema.sql
psql -h localhost -U secadmin -d secdb -f functions.sql

# Mosquitto
sudo apt install -y mosquitto mosquitto-clients
sudo mosquitto_passwd -c /etc/mosquitto/passwd serverapp
sudo cp mosquitto/default.conf /etc/mosquitto/conf.d/default.conf
sudo systemctl restart mosquitto

# Node-RED (32-bit: usar o nodejs do apt, não o script oficial)
sudo apt install -y nodejs npm
sudo npm install -g --unsafe-perm node-red@4
# instalar o nó node-red-contrib-postgresql pelo Manage Palette

# Push (FCM)
cd push-service && npm install
# colocar a chave do Firebase em push-service/secbox-sa.json
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

> Nota de implementação: no nó `mqtt in` do Node-RED, o payload chega como Buffer;
> as funções fazem parse defensivo (`Buffer` → string → `JSON.parse`) antes de usar.
