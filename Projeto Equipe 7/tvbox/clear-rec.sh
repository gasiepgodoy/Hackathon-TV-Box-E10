#!/bin/bash
# Apaga todas as gravações da câmera e mostra o espaço livre.
find /opt/mediamtx/rec/ -type f -delete
echo "Gravações apagadas."
df -h / | awk 'NR==1 || /\/$/'
