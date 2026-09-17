#!/bin/bash
while true; do
  cd /root/aqua-fl

  /usr/bin/python3 -m fluxos.edgebox.edgebox_node >> logs/edgebox_loop.log 2>&1

  sleep 2
done
