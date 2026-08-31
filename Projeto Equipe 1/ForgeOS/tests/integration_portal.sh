#!/bin/bash
# Teste de integração do portal — roda na própria box via LAN.
# Ciclo completo: status → provision inválido → rollback AP → reset.
BASE_URL=http://127.0.0.1:8080
STATE=/opt/forgeos/state
pass=0; fail=0
ck() { if eval "$2" >/dev/null 2>&1; then echo "PASS: $1"; pass=$((pass+1)); else echo "FAIL: $1"; fail=$((fail+1)); fi; }

echo "=== 1. Portal e rede ==="
ck "GET /api/status responde 200"      "curl -fsS $BASE_URL/api/status"
ck "index contém MultiForge"           "curl -fsS $BASE_URL/ | grep -q MultiForge"
ck "pico.min.css servido"              "curl -fsS $BASE_URL/static/css/pico.min.css | head -c100"
ck "dnsmasq cativo escuta :53"         "ss -uln | grep ':53 '"
ck "portal escuta :8080"               "ss -ltn | grep ':8080 '"
ck "AP ativo (wpa_supplicant mode=2)"  "pgrep -f 'wpa_supplicant.*wpa_ap.conf'"

echo "=== 2. Validação de entrada ==="
C1=$(curl -s -o /tmp/r1.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"mode":"psk","ssid":"x","password":"123"}' $BASE_URL/api/provision)
ck "rejeita senha curta (HTTP 400)"    "[ '$C1' = '400' ]"
C2=$(curl -s -o /tmp/r2.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"mode":"eap","ssid":"eduroam","method":"PEAP","phase2":"MSCHAPV2","identity":"","password":"p"}' $BASE_URL/api/provision)
ck "rejeita EAP sem identidade (400)"  "[ '$C2' = '400' ]"

echo "=== 3. Ciclo de provisionamento inválido (rollback) ==="
rm -f $STATE/result.json
C3=$(curl -s -o /tmp/r3.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"mode":"psk","ssid":"ForgeTest-NonExist","password":"12345678"}' $BASE_URL/api/provision)
ck "POST /api/provision aceito (200)"  "[ '$C3' = '200' ]"
ck "resposta contém ok"                "grep -q 'ok' /tmp/r3.json"

AP=no
for i in $(seq 1 24); do
    sleep 5
    ST=$(grep -o '"status": *"failed"' $STATE/result.json 2>/dev/null)
    pgrep -f 'wpa_supplicant.*wpa_ap.conf' >/dev/null && AP=yes
    [ -n "$ST" ] && [ "$AP" = "yes" ] && break
done
ck "resultado 'failed' registrado (≤120s)" "grep -q failed $STATE/result.json"
ck "AP restaurado automaticamente"          "[ '$AP' = 'yes' ]"
P=no
for i in $(seq 1 10); do
    curl -fsS $BASE_URL/api/status >/dev/null 2>&1 && { P=yes; break; }
    sleep 2
done
ck "portal reativado pós-rollback (≤20s)"   "[ '$P' = 'yes' ]"

echo "=== 4. Reset ==="
curl -fsS -X POST $BASE_URL/api/reset >/dev/null
sleep 4
ck "reset restaura modo AP"            "curl -fsS $BASE_URL/api/status | grep -q '\"ap_active\": true'"

echo
echo "RESULTADO: $pass PASS / $fail FAIL"
[ $fail -eq 0 ]
