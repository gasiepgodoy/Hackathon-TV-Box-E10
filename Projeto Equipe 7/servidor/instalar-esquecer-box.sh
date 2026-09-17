#!/bin/bash
# Instala no servidor o "esquecer a GuardianBox": a função forget_device no
# banco e o fluxo POST /api/forget-device no Node-RED.
#
# Pede duas senhas, nenhuma gravada nem impressa: a do sudo (para o psql) e a
# do editor do Node-RED (o adminAuth bloqueia publicar fluxo sem ela).
#
# Uso, de dentro da pasta servidor/ copiada para o servidor:
#   bash instalar-esquecer-box.sh
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
NR=http://localhost:1880
FLUXO="$AQUI/nodered/api-esquecer.json"

falhar() { echo "ERRO: $*" >&2; exit 1; }
[ -f "$AQUI/functions.sql" ] || falhar "functions.sql não encontrado em $AQUI"
[ -f "$FLUXO" ] || falhar "$FLUXO não encontrado"

echo "== 1/3 banco: função forget_device =="
# functions.sql inteiro: todas as funções são CREATE OR REPLACE, e o arquivo é
# a fonte da verdade. -1 = tudo numa transação só.
# Pela entrada padrão: o usuário postgres não lê arquivos dentro da pasta
# pessoal, e o redirecionamento é aberto por quem roda o script.
sudo -u postgres psql -q -1 -d secdb -v ON_ERROR_STOP=1 -f - < "$AQUI/functions.sql" \
    || falhar "o psql recusou o functions.sql; nada foi alterado no banco"
sudo -u postgres psql -d secdb -tAc \
    "SELECT 'forget_device presente: ' || count(*) FROM pg_proc WHERE proname='forget_device'"

echo
echo "== 2/3 Node-RED: entrar =="
read -rsp "Senha do editor do Node-RED (usuário admin): " senha; echo
TOKEN=$(printf '%s' "$senha" | curl -s --max-time 15 -X POST "$NR/auth/token" \
    --data-urlencode client_id=node-red-admin \
    --data-urlencode grant_type=password \
    --data-urlencode 'scope=*' \
    --data-urlencode username=admin \
    --data-urlencode password@- \
    | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("access_token",""))
except Exception: print("")')
unset senha
[ -n "$TOKEN" ] || falhar "o Node-RED recusou a senha"

echo "== 3/3 Node-RED: publicar o fluxo =="
# Acrescenta aos fluxos vivos em vez de importar: os nós de configuração com as
# credenciais do banco e do broker não estão no repositório de propósito, e
# uma publicação completa a partir dos arquivos os apagaria.
NR_TOKEN="$TOKEN" python3 - "$FLUXO" <<'PY' || falhar "não publiquei o fluxo"
import json, os, sys, urllib.request
NR = "http://localhost:1880"
tok = os.environ["NR_TOKEN"]
def req(metodo, caminho, corpo=None, extra=None):
    h = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
    h.update(extra or {})
    dado = None if corpo is None else json.dumps(corpo).encode()
    r = urllib.request.Request(NR + caminho, data=dado, headers=h, method=metodo)
    with urllib.request.urlopen(r, timeout=60) as resp:
        t = resp.read()
        return resp.status, (json.loads(t) if t else None)
novos = json.load(open(sys.argv[1], encoding="utf-8"))
_, vivos = req("GET", "/flows")
ids_vivos = {n["id"] for n in vivos}
if any(n.get("url") == "/api/forget-device" for n in vivos):
    print("o fluxo já estava publicado; nada a fazer")
    sys.exit(0)
choque = [n["id"] for n in novos if n["id"] in ids_vivos]
if choque:
    sys.exit("ids já em uso: %s" % choque)
for dep in ("pg_secdb", "mqtt_broker_local"):
    if dep not in ids_vivos:
        sys.exit("nó de configuração %s não existe no Node-RED" % dep)
st, _ = req("POST", "/flows", vivos + novos, {"Node-RED-Deployment-Type": "full"})
print("publicado (http %d), %d nós novos" % (st, len(novos)))
PY

sleep 4
echo
echo "== conferência =="
printf '  /api/forget-device sem sessão -> %s  (400 = rota viva)\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST \
        -H 'Content-Type: application/json' -d '{}' "$NR/api/forget-device")"
printf '  sessão inválida               -> %s  (403 = recusou sem revelar nada)\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST \
        -H 'Content-Type: application/json' -H 'Authorization: Bearer invalida' \
        -d '{"device":"TVB-NAOEXISTE"}' "$NR/api/forget-device")"
echo
echo "Pronto."
