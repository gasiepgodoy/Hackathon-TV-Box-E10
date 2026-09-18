<div align="center">

  <img src="static/logo.png" alt="SmartFlow Box Logo" width="180" style="border-radius: 20%;">

  # SmartFlow Box

  **Monitoramento de Filas e Fluxo de Atendimento via Visão Computacional em Dispositivos Embarcados**

  [![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
  [![YOLOv8](https://img.shields.io/badge/YOLOv8-ONNX-00FFFF?style=for-the-badge)](https://docs.ultralytics.com/)

</div>

---

### 👥 Membros da Equipe (Equipe 5)

* **Bryan Xavier Kufta**
* **Guilherme Henrique Pinheiro**
* **Vinicius Gabriel Barros**

---

## 📌 Sobre o Projeto

* **A Solução:** O **SmartFlow Box** é uma solução de visão computacional projetada para operar em hardware restrito (como TV Boxes/SBCs rodando Linux). O sistema monitora e analisa o fluxo de pessoas em tempo real.
* **O Objetivo:** Calcular e exibir o tempo estimado de espera combinando a contagem de pessoas na fila com o ritmo e número de atendentes em serviço.
* **Para que serve:** Detectar a presença de usuários e funcionários em áreas delimitadas (ROIs), automatizando as métricas de tempo e vazão do local.
* **Aplicação Principal:** Gestão inteligente de filas de atendimento, validada e aplicada no **Restaurante Universitário (RU)** para otimizar o tempo dos estudantes e mitigar congestionamentos nos horários de pico.

---

## 🛠️ Tecnologias Utilizadas

* **Python 3** (Linguagem Principal)
* **YOLOv8 (ONNX/PyTorch)** (Detecção de Pessoas otimizada em CPU via OpenCV DNN)
* **OpenCV** (Processamento de Imagem, Renderização de Bounding Boxes e Stream MJPEG)
* **Flask** (Servidor Web, Servidor de Streaming e Endpoints da API REST)
* **Shapely** (Cálculos Geométricos para Verificação de Interseção Ponto-em-Polígono)
* **SQLite3** (Armazenamento Local Persistente do Histórico de Fluxo)
* **Chart.js & HTML5 Canvas** (Dashboard Dinâmico Responsivo com Suporte a Gestos de Toque/Clique)
* **pytz** (Gerenciamento de Fuso Horário Local - America/Sao_Paulo)[cite: 17]

---

## 📁 Estrutura do Repositório

```text
Projeto Equipe 5/
├── static/
│   └── logo.png         # Logotipo do projeto exibido no cabeçalho do dashboard
├── templates/
│   └── index.html       # Dashboard responsivo com Player HTML5/Canvas e Gráficos
├── main.py              # Servidor Flask, Thread da IA e Lógica das ROIs
├── requirements.txt     # Lista de dependências Python
├── yolov8n.onnx         # Modelo YOLOv8 otimizado para inferência rápida via OpenCV DNN
├── yolov8n.pt           # Pesos originais do YOLOv8 (PyTorch)
├── README.md            # Documentação oficial do projeto
├── (config_roi.json)    # Gerado dinamicamente ao marcar as ROIs pela interface web
└── (banco_dados.db)     # Banco SQLite criado automaticamente na primeira execução
