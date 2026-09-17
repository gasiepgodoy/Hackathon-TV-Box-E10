#!/bin/bash
while true; do
  cd /root/aqua-fl

  if [ -f /root/aqua-fl/dados/edgebox/edgebox_autoencoder_model.json ]; then
    /usr/bin/python3 -m fluxos.edgebox.edgebox_autoencoder infer >> logs/edgebox_autoencoder.log 2>&1
  fi

  if [ -f /root/aqua-fl/fluxos/edgebox/edgebox_site_autoencoder.py ]; then
    /usr/bin/python3 -m fluxos.edgebox.edgebox_site_autoencoder >> logs/edgebox_site.log 2>&1
  fi

  if [ -f /root/aqua-fl/fluxos/edgebox/edgebox_db_sync.py ]; then
    /usr/bin/python3 -m fluxos.edgebox.edgebox_db_sync >> logs/edgebox_db.log 2>&1
  fi

  sleep 10
done
