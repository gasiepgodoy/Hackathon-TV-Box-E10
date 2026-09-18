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
* **pytz** (Gerenciamento de Fuso Horário Local - America/Sao_Paulo)

---

## 📁 Estrutura do Repositório

* `static/logo.png` — Logotipo do projeto exibido no cabeçalho do dashboard
* `templates/index.html` — Dashboard responsivo com Player HTML5/Canvas e Gráficos
* `main.py` — Servidor Flask, Thread da IA e Lógica das ROIs
* `requirements.txt` — Lista de dependências Python
* `yolov8n.onnx` — Modelo YOLOv8 otimizado para inferência rápida via OpenCV DNN
* `yolov8n.pt` — Pesos originais do YOLOv8 (PyTorch)
* `README.md` — Documentação oficial do projeto
* *(config_roi.json)* — Gerado dinamicamente ao marcar as ROIs pela interface web
* *(banco_dados.db)* — Banco SQLite criado automaticamente na primeira execução

---

## 🚀 Como Executar

1. **Sincronizar Fuso Horário do Sistema (Linux):**  
   `timedatectl set-timezone America/Sao_Paulo`  
   `localectl set-locale LC_TIME=pt_BR.UTF-8`

2. **Configurar e Ativar o Ambiente Virtual Python:**  
   `python3 -m venv venv`  
   `source venv/bin/activate`

3. **Instalar Dependências:**  
   `pip install -r requirements.txt`

4. **Iniciar a Aplicação:**  
   `python main.py`

---

## 🖥️ Como Utilizar a Interface Web

1. Acesse o painel pelo navegador em qualquer dispositivo na mesma rede: `http://<IP_DO_DISPOSITIVO>:5000`.
2. **Marcação da ROI da Fila (Contorno Vermelho):**  
   * Clique no botão **Marcar ROI Fila (Vermelho)**.
   * Toque ou clique em 4 pontos sobre o vídeo para delimitar a área da fila. O envio utiliza coordenadas normalizadas para garantir precisão em qualquer resolução ou tamanho de tela.
3. **Marcação da ROI de Atendimento (Contorno Amarelo):**  
   * Clique no botão **Marcar ROI Atendimento (Amarelo)**.
   * Toque ou clique em 4 pontos no vídeo para delimitar a área onde os funcionários atuam.
4. **Interpretação Visual:**  
   * **Verde:** Pessoas identificadas na Fila.
   * **Laranja:** Pessoas identificadas no Atendimento.
   * **Azul:** Pessoas fora das ROIs delimitadas.
5. **Gerenciamento do Painel:**  
   * **Limpar ROIs:** Apaga o mapa de áreas para refazer as marcações.
   * **Zerar Histórico:** Apaga os registros acumulados no SQLite para o dia atual.
   * **Análise Histórica:** Selecione os dias da semana nos seletores do dashboard para analisar o comportamento histórico dos horários de pico.
