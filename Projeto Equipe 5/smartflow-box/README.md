# SmartFlow Box

> **Monitoramento de Filas e Fluxo de Atendimento via Visão Computacional em Dispositivos Embarcados**

## 📌 Sobre o Projeto

O **SmartFlow Box** é uma solução de visão computacional projetada para operar em hardware restrito (como TV Boxes/SBCs rodando Linux). O sistema monitora e analisa o fluxo de pessoas em tempo real, calculando o tempo estimado de espera ao integrar a contagem de pessoas na fila com o número de atendentes em serviço.

O monitoramento utiliza **Regiões de Interesse (ROIs)** dinâmicas demarcadas pelo usuário diretamente em um Canvas HTML5 responsivo na interface web. As métricas e o histórico de pico são armazenados localmente e exibidos em um painel em tempo real. Sua aplicação principal foi validada no **Restaurante Universitário (RU)** para aumentar a previsibilidade nos horários de almoço.

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

* **main.py**: Aplicação principal (Servidor Flask, Thread da IA e Lógica das ROIs)
* **yolov8n.onnx**: Modelo YOLOv8 otimizado para inferência rápida via OpenCV DNN
* **yolov8n.pt**: Pesos originais do YOLOv8 (PyTorch)
* **static/logo.png**: Logotipo do projeto exibido no cabeçalho do dashboard
* **templates/index.html**: Dashboard responsivo com Player HTML5/Canvas e Gráficos
* **requirements.txt**: Lista de dependências Python
* **README.md**: Documentação do projeto
* *(config_roi.json)*: Gerado dinamicamente ao marcar as ROIs pela interface web
* *(banco_dados.db)*: Banco SQLite criado automaticamente na primeira execução

---

## 🚀 Como Executar

1. **Preparar o diretório:**  
   `cd /root/smartflow-box`

2. **Sincronizar Fuso Horário do Sistema (Linux):**  
   `timedatectl set-timezone America/Sao_Paulo`  
   `localectl set-locale LC_TIME=pt_BR.UTF-8`

3. **Configurar o Ambiente Virtual Python:**  
   `python3 -m venv venv`  
   `source venv/bin/activate`

4. **Instalar as Dependências:**  
   `pip install -r requirements.txt`

5. **Executar a Aplicação:**  
   `python main.py`

---

## 🖥️ Como Utilizar a Interface Web

1. Acesse o painel pelo navegador de qualquer dispositivo na mesma rede: `http://<IP_DO_DISPOSITIVO>:5000`.
2. **Marcação da ROI da Fila (Contorno Vermelho):**
   * Clique no botão **Marcar ROI Fila (Vermelho)**.
   * Toque ou clique em 4 pontos sobre o vídeo para delimitar a área da fila. O envio utiliza coordenadas normalizadas para garantir precisão em qualquer resolução ou tamanho de tela.
3. **Marcação da ROI de Atendimento (Contorno Amarelo):**
   * Clique no botão **Marcar ROI Atendimento (Amarelo)**.
   * Toque ou clique em 4 pontos no vídeo para delimitar a área onde os funcionários atuam.
4. **Interpretação Visual:**
   * Pessoas identificadas na **Fila** recebem uma caixa de seleção **Verde**.
   * Pessoas identificadas no **Atendimento** recebem uma caixa **Laranja**.
   * Pessoas fora das ROIs mantêm a caixa **Azul**.
5. **Gerenciamento do Painel:**
   * Utilize o botão **Limpar ROIs** para apagar o mapa de áreas e refazer as marcações.
   * Utilize o botão **Zerar Histórico** para apagar os registros acumulados no SQLite para o dia atual.
   * Selecione os dias da semana nos seletores do dashboard para analisar o comportamento histórico de horários de pico.
