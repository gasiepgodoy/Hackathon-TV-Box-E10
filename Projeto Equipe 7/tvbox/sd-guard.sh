#!/bin/bash
# Rede de segurança do cartão: apaga as gravações mais antigas quando o uso
# do "/" passa do limiar, evitando encher o disco e travar a box.
REC="/opt/mediamtx/rec"
THRESHOLD=85   # % de uso máximo
usage() { df --output=pcent / | tail -1 | tr -dc '0-9'; }
while [ "$(usage)" -ge "$THRESHOLD" ]; do
    oldest=$(find "$REC" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)
    [ -z "$oldest" ] && break
    rm -f "$oldest"
done
