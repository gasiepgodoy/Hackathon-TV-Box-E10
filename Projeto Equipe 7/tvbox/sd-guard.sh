#!/bin/bash
# Rede de segurança do cartão: apaga as gravações mais antigas quando o uso do
# disco de gravação passa do limiar, evitando enchê-lo até parar de gravar.
REC="/opt/mediamtx/rec"
THRESHOLD=85   # % de uso máximo
# Mede o sistema de arquivos DA GRAVAÇÃO, não o "/". Desde que o sistema foi
# para a eMMC e o cartão virou disco de dados, são dois: olhando o "/", este
# guarda veria a eMMC parada em 46% e nunca apagaria nada, enquanto o cartão
# enchia até 100%.
usage() { df --output=pcent "$REC" | tail -1 | tr -dc '0-9'; }

# Sem o cartão montado, REC é um diretório na eMMC e apagar ali não faria
# sentido -- e o diretório está marcado imutável de propósito. Sai quieto.
if [ "$(stat -c %d "$REC" 2>/dev/null)" = "$(stat -c %d / 2>/dev/null)" ]; then
    echo "cartao de gravacao nao montado; nada a fazer" >&2
    exit 0
fi

# Segmentos de 0 byte sobram quando a box perde energia durante a gravação, e um
# só deles faz a API de playback devolver {"status":"error","error":"EOF"},
# derrubando a linha do tempo inteira no app.
find "$REC" -type f -size 0 -delete 2>/dev/null
while [ "$(usage)" -ge "$THRESHOLD" ]; do
    oldest=$(find "$REC" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)
    [ -z "$oldest" ] && break
    rm -f "$oldest"
done
