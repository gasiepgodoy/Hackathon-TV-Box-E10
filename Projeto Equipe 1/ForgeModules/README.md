# ForgeModules

Diretorio central de aplicacoes modulares compativeis com o ecossistema ForgeOS. Cada modulo representa um servico independente acompanhado de seu manifesto declarativo (`module.yaml`), requisitos de hardware e rotinas de ciclo de vida.

---

## Modulos Disponíveis

| Modulo | Categoria | Descricao | Stack | Estado |
|--------|-----------|-----------|-------|--------|
| **[totem](totem/)** | AI / Voz | Mina - Assistente Virtual Acadêmica para quiosques com voz offline e GUI | Python 3, PyQt5, Sherpa-ONNX, SQLite | Estavel |
| **[web-scraping](sub-modulos/web-scraping/)** | Dados / RAG | Coletor assincrono de dados universitarios com API FastAPI e agente LangChain | Python 3.12, FastAPI, PostgreSQL/SQLite, LangChain | Homologado |

---

## Estrutura do Manifesto (`module.yaml`)

Para que o ForgeOS e o Portal Web gerenciem a aplicacao, o modulo deve conter um arquivo `module.yaml` padronizado:

```yaml
id: nome-do-modulo
name: "Nome do Modulo"
version: "1.0.0"
description: "Descricao funcional da aplicacao"
category: ai # ai | data | display | iot | tools
author: "Autor ou Organizacao"
license: MIT

requirements:
  min_ram_mb: 512
  min_storage_mb: 300
  python: ">=3.9"
  system_packages:
    - build-essential
    - python3-dev

source:
  type: local # local ou git
  path: "ForgeModules/nome-do-modulo"

lifecycle:
  install: "python install.py"
  start: "python main.py"
  stop: "pkill -f main.py"
  healthcheck: "curl -f http://localhost:5000/health"
  systemd_unit: "forge-nome-do-modulo.service"

conflicts_with:
  - web-scraping
```

---

## Ciclo de Vida e Execução

Os modulos sao controlados pelo Portal ForgeOS ou por linha de comando:

1. **Descoberta:** O portal le o catalogo em `ForgeDB/modules/catalog.yaml` e os manifestos `module.yaml`.
2. **Instalacao:** Executa a rotina `lifecycle.install` para configuracao de dependencias e compilacao de extensoes.
3. **Execucao:** Executa a rotina `lifecycle.start` ou inicializa a unidade do systemd associada.
4. **Monitoramento:** Avalia o estado do processo atraves do comando `lifecycle.healthcheck`.
5. **Parada / Remocao:** Executa `lifecycle.stop` e limpa os arquivos temporarios.

---

## Cadastro de Novos Módulos

1. Crie o diretorio em `ForgeModules/<nome-modulo>/`.
2. Adicione o arquivo `module.yaml` definindo requisitos e comandos de ciclo de vida.
3. Cadastre a referencia no arquivo central `ForgeDB/modules/catalog.yaml`.
4. Valide a sintaxe do arquivo contra o schema formal:
   ```bash
   python -c "import yaml, json, jsonschema; jsonschema.validate(yaml.safe_load(open('ForgeModules/<nome-modulo>/module.yaml')), json.load(open('ForgeDB/schemas/module.schema.json'))); print('Manifesto valido.')"
   ```
