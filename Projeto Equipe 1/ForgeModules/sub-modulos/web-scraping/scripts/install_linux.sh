#!/usr/bin/env bash
# Script de instalação para Ubuntu 24.04 e derivados
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "==> Assistente Acadêmico Local — Instalação"
echo "    Diretório: $PROJECT_DIR"

# Dependências do sistema
echo "==> Instalando dependências do sistema..."
sudo apt-get update
sudo apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    docker.io \
    docker-compose-v2 \
    curl \
    git

# Docker sem sudo (opcional)
if ! groups "$USER" | grep -q docker; then
    echo "==> Adicionando usuário ao grupo docker..."
    sudo usermod -aG docker "$USER"
    echo "    Faça logout/login para usar Docker sem sudo."
fi

# Ambiente virtual Python
echo "==> Criando ambiente virtual..."
python3.12 -m venv .venv
source .venv/bin/activate

echo "==> Instalando dependências Python..."
pip install --upgrade pip
pip install -r requirements.txt

# Arquivo .env
if [ ! -f .env ]; then
    echo "==> Criando .env a partir de .env.example..."
    cp .env.example .env
fi

# Subir serviços
echo "==> Iniciando containers Docker..."
docker compose up -d --build

echo ""
echo "=========================================="
echo " Instalação concluída!"
echo " Dashboard: http://localhost:8000"
echo " API docs:  http://localhost:8000/docs"
echo ""
echo " Comandos úteis:"
echo "   docker compose logs -f collector"
echo "   docker compose logs -f api"
echo "   source .venv/bin/activate && pytest"
echo "=========================================="
