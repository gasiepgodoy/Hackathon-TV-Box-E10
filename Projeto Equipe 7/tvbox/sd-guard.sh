#!/bin/bash
# Rede de segurança do cartão: apaga as gravações mais antigas quando o uso
# do "/" passa do limiar, evitando encher o disco e travar a box.
REC="/opt/mediamtx/rec"
THRESHOLD=85   # % de uso máximo
usage() { df --output=pcent / | tail -1 | tr -dc '0-9'; }

# Segmentos de 0 byte sobram quando a box perde energia durante a gravação, e um
# só deles faz a API de playback devolver {"status":"error","error":"EOF"},
# derrubando a linha do tempo inteira no app.
find "$REC" -type f -size 0 -delete 2>/dev/null
while [ "$(usage)" -ge "$THRESHOLD" ]; do
    oldest=$(find "$REC" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)
    [ -z "$oldest" ] && break
    rm -f "$oldest"
done
