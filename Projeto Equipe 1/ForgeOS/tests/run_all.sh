#!/bin/bash
# Runner geral: unitários + integração
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "########## UNITÁRIOS ##########"
python3 "$DIR/test_units.py" 2>&1
U=$?
echo
echo "########## INTEGRAÇÃO ##########"
bash "$DIR/integration_portal.sh" 2>&1
I=$?
echo
echo "########## RESUMO ##########"
echo "unitários: $([ $U -eq 0 ] && echo OK || echo FALHOU) | integração: $([ $I -eq 0 ] && echo OK || echo FALHOU)"
[ $U -eq 0 ] && [ $I -eq 0 ]
