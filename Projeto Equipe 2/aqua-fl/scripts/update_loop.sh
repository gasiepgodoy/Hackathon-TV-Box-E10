#!/bin/bash
while true; do
  cd /root/aqua-fl
  /usr/bin/python3 -m fluxos.clima.aqua_fl_demo > logs/update.log 2>&1
  sleep 60
done
