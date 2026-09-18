<div align="center">

  <img src="static/logo.png" alt="SmartFlow Box Logo" width="180" style="border-radius: 20%;">

  # SmartFlow Box

  **Monitoramento de Filas e Fluxo de Atendimento via Visão Computacional em Dispositivos Embarcados**

  [![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
  [![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
  [![YOLOv8](https://img.shields.io/badge/YOLOv8-ONNX-00FFFF?style=for-the-badge)](https://docs.ultralytics.com/)
  [![Debian](https://img.shields.io/badge/Debian-13-A81D33?style=for-the-badge&logo=debian&logoColor=white)](https://www.debian.org/)

</div>

---

### 👥 Membros da Equipe (Equipe 5)

* **Bryan Xavier Kufta**
* **Guilherme Henrique Pinheiro**
* **Vinicius Gabriel Barros**

---

## 📌 Visão Geral do Projeto

O **SmartFlow Box** é um sistema embarcado autônomo de visão computacional desenvolvido para monitorar, contabilizar e analisar o fluxo de pessoas e filas de espera em tempo real. Projetado para operar em hardware de baixo custo e com recursos computacionais restritos (como TV Boxes/SBCs rodando sistemas Linux Server minimalistas), a solução substitui sensores infravermelhos custosos ou contagens manuais imprecisas por uma pipeline otimizada de Inteligência Artificial.

A validação prática do sistema foi realizada no contexto do **Restaurante Universitário (RU)**, onde o congestionamento em horários de pico afeta diretamente a rotina acadêmica. A solução permite aos usuários e gestores visualizarem o tempo estimado de fila, ocupação atual e histórico de demanda diretamente via navegador web.

---

## 🏗️ Arquitetura e Fluxo de Dados

A aplicação opera através de um modelo multi-thread assíncrono para garantir estabilidade no streaming de vídeo e alta frequência na inferência de IA sem bloquear as requisições HTTP do servidor web.

<pre><code>[ Câmera / Stream RTSP / Arquivo Vídeo ]
                  │
                  ▼
         ┌─────────────────┐
         │  Thread de IA   │ ◄── [ Processamento OpenCV DNN + YOLOv8 ONNX ]
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Interseção ROI  │ ◄── [ Algoritmo Shapely: Ponto-em-Polígono ]
         └────────┬────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌──────────────┐    ┌───────────────┐
│ Banco SQLite │    │ Streaming Web │ (MJPEG via Flask)
└──────────────┘    └───────────────┘</code></pre>

1. **Captura & Pré-processamento:** Leitura dos frames e redimensionamento para a resolução de entrada da rede neural.
2. **Inferência Otimizada (CPU):** Processamento do modelo YOLOv8 Nano exportado em formato ONNX via engine `cv2.dnn`.
3. **Análise de Regiões de Interesse (ROIs):** Mapeamento do ponto central inferior (*bottom-center*) da caixa delimitadora (*bounding box*) de cada pessoa detectada. Verificação geométrica via biblioteca `Shapely` para identificar se o indivíduo está na área de **Fila (Vermelho)** ou **Atendimento (Amarelo)**.
4. **Persistência & Métricas:** Armazenamento periódico das contagens agregadas no banco SQLite e cálculo dinâmico da estimativa de tempo de espera.
5. **Apresentação Web:** Servidor Flask entrega a interface responsiva em HTML5 Canvas e atualiza os gráficos via requisições assíncronas.

---

## 🧠 Métricas e Algoritmo de Estimativa

O tempo estimado de espera na fila é calculated dinamicamente combinando o volume de pessoas aguardando com o ritmo de vazão dos atendentes em serviço:

* **Pessoas na Fila ($N_{fila}$):** Total de pessoas detectadas dentro do polígono vermelho.
* **Atendentes em Serviço ($N_{atend}$):** Total de funcionários detectados dentro do polígono amarelo.
* **Tempo Médio de Atendimento por Pessoa ($T_{atend}$):** Constante operacional calibrada conforme o histórico do local (ex: $20$ segundos por usuário).

$$\text{Tempo Estimado (min)} = \frac{N_{\text{fila}} \times T_{\text{atend}}}{\max(N_{\text{atend}}, 1) \times 60}$$

---

## ⚡ Desafios e Soluções para Hardware Embarcado

Operar redes neurais profundas em hardware de baixo custo apresenta limitações severas de CPU e memória RAM. O projeto resolveu essas restrições através das seguintes estratégias:

* **Conversão PyTorch ➔ ONNX:** A execução do modelo original PyTorch gerava alto consumo de memória. O modelo foi convertido para o formato aberto ONNX, permitindo o uso da execução nativa e otimizada do OpenCV DNN em linguagem C++.
* **Resolução Otimizada de Inferência:** Redução do tamanho da imagem enviada para a rede neural sem comprometer a acurácia na detecção de classe única (*person*).
* **Processamento de Ponto-em-Polígono Leve:** Cálculo geométrico restrito apenas às coordenadas da base dos pés do indivíduo, reduzindo operações matemáticas complexas.

---

## 🛠️ Tecnologias Utilizadas

* **Python 3.10+**: Linguagem principal do ecossistema.
* **YOLOv8 Nano (ONNX)**: Modelo de detecção de objetos de última geração otimizado para CPU.
* **OpenCV 4.x**: Manipulação de matrizes de vídeo, inferência de rede neural e geração do fluxo MJPEG.
* **Flask**: Micro-framework web para exposição da interface e endpoints da API.
* **Shapely**: Biblioteca de análise espacial e geometrias planares.
* **SQLite3**: Banco de dados relacional embutido e de baixíssimo consumo de I/O.
* **Chart.js & HTML5 Canvas**: Visualização dinâmica e interativa de dados no cliente.
* **pytz**: Normalização de fuso horário local (`America/Sao_Paulo`).

---

## 📁 Estrutura do Repositório

<pre><code>Projeto Equipe 5/
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
└── (banco_dados.db)     # Banco SQLite criado automaticamente na primeira execução</code></pre>

---

## 🌐 Endpoints da API REST

A interface do sistema comunica-se com o backend via rotas RESTful:

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/` | Retorna o Dashboard HTML5 principal. |
| `GET` | `/video_feed` | Stream de vídeo contínuo em formato Multipart MJPEG. |
| `POST` | `/salvar_roi` | Salva as coordenadas dos polígonos da Fila e Atendimento no `config_roi.json`. |
| `POST` | `/limpar_roi` | Remove as configurações de polígonos salvos. |
| `GET` | `/dados_atualizados` | Retorna o JSON contendo contagem atual, atendentes e tempo estimado. |
| `GET` | `/historico` | Retorna o histórico do dia selecionado para renderização dos gráficos no Chart.js. |
| `POST` | `/zerar_historico` | Apaga os registros do banco de dados do dia atual. |

---

## 🚀 Como Executar (Guia Passo a Passo)

### 1. Preparar o Ambiente Debian / Linux
Certifique-se de que o gerenciador de pacotes do Python e o módulo de ambientes virtuais estão instalados no sistema operacional:
`sudo apt update && sudo apt install -y python3-pip python3-venv`

### 2. Sincronizar Fuso Horário do Sistema
Garante que o banco SQLite grave os timestamps corretos em horário local de Brasília:
`sudo timedatectl set-timezone America/Sao_Paulo`  
`sudo localectl set-locale LC_TIME=pt_BR.UTF-8`

### 3. Configurar e Ativar o Ambiente Virtual
Isola as dependências do projeto para evitar conflitos com pacotes do sistema:
`python3 -m venv venv`  
`source venv/bin/activate`

### 4. Instalar as Dependências
Instala as bibliotecas Python necessárias listadas no repositório:
`pip install --upgrade pip`  
`pip install -r requirements.txt`

### 5. Iniciar a Aplicação
Executa a aplicação e inicia o servidor web na porta 5000:
`python main.py`

---

## 🖥️ Como Utilizar a Interface Web

1. **Acesso:** Acesse `http://<IP_DO_DISPOSITIVO>:5000` via navegador na mesma rede local.
2. **Delimitação das Zonas (ROIs):**
   * **Fila:** Clique em **Marcar ROI Fila (Vermelho)** e selecione 4 pontos no vídeo demarcando a fila de espera.
   * **Atendimento:** Clique em **Marcar ROI Atendimento (Amarelo)** e selecione 4 pontos demarcando o espaço de trabalho dos atendentes.
3. **Leitura Visual das Detecções:**
   * 🟢 **Verde:** Usuário identificado aguardando na fila.
   * 🟠 **Laranja:** Funcionário/Atendente em serviço.
   * 🔵 **Azul:** Pessoas fora das zonas de interesse.
4. **Controle e Análise:**
   * **Limpar ROIs:** Redefine o mapeamento de áreas.
   * **Zerar Histórico:** Reseta as estatísticas salvas no dia.
   * **Painel Histórico:** Selecione dias anteriores nos seletores para visualizar gráficos de tendência e horários de pico.
