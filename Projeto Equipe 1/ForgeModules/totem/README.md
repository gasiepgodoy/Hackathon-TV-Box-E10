# Mina - Assistente Virtual de Voz Acadêmica (G.E.R.A - UNESP Sorocaba)

Mina é uma assistente virtual de voz interativa e inteligente, construída para operar de forma híbrida e eficiente. Ela serve como assistente acadêmico para os alunos da **UNESP Sorocaba**, sendo capaz de rodar localmente (offline) em hardware de baixo recurso (como TV Boxes e Orange Pi) e realizar consultas dinâmicas de salas, professores, horários e notícias acadêmicas.

---

## 🛠️ Principais Recursos

1. **Modo Híbrido (Local + Nuvem):**
   * **Inteligência Local (MABI Intent Classifier):** Intercepta e processa consultas acadêmicas recorrentes (salas de professores, horários de aula, notícias e cantina) localmente, sem custos de API ou latência de rede.
   * **Inteligência em Nuvem (LLM Fallback):** Caso o comando não seja de escopo local acadêmico, a dúvida é enviada para a API (Cerebras/Groq) de forma transparente.
2. **Entrada de Voz Local (STT):**
   * Transcrição de áudio do microfone usando a API Groq (Whisper).
3. **Síntese de Voz Local (TTS):**
   * Geração de fala com entonação natural em português usando o motor local `edge-tts` com o cliente `TTSClient`.
4. **Detecção de Wake Word (Keyword Spotting):**
   * Daemon integrado com `sherpa-onnx` que escuta continuamente por *"Alexa"* ou *"Hey Jarvis"* de forma 100% offline, emitindo um sinal sonoro de confirmação ao ser ativado.
5. **Interface Gráfica e Linha de Comando:**
   * **Modo CLI:** Loop interativo de console (`main_cli.py`).
   * **Modo GUI:** Interface gráfica moderna construída com `PyQt5` e sincronização assíncrona de emoções em tempo real (`main_gui.py`), incluindo tela de descanso NTP rotativa e otimizações avançadas de QML.
6. **Sincronização de Tempo (NTP):**
   * A interface gráfica (`GUI`) utiliza um offset de tempo NTP persistente para garantir precisão do relógio em dispositivos sem RTC, sincronizando offline por meio do `memory.db`.

---

## 📂 Arquitetura do Repositório

```
Mina-a-Assistente-Virtual/
├── config/
│   └── prompts.txt           # Prompt do sistema (Fallback)
├── models/                   # Modelos locais (Wake Word, parâmetros de voz e o classificador SVM MABI)
├── src/
│   ├── display/              # Renderização e gerência da GUI (PyQt5)
│   └── utils/
│       ├── academic_db.py    # Banco de dados SQLite acadêmico local (academic.db)
│       ├── chat_bridge.py    # Gerenciador da conexão com LLMs / APICOMM
│       ├── intent_classifier.py # Classificador de intenções local e offline (MABI)
│       ├── stt_client.py     # Transcritor local (PortAudio + C bindings)
│       ├── tts_client.py     # Sintetizador local (edge-tts + miniaudio)
│       └── ntp_sync.py       # Sincronização de horário NTP com cache em SQLite
├── scripts/                  # Scripts de sincronização e utilitários
│   ├── mabi_voice_interface.py # Script integrado de demonstração rápida acústica local MABI
│   ├── mina_wakeword_daemon.py # Daemon de monitoramento de Wake Word
│   └── unesp_scraper.py      # Coletor em segundo plano do portal UNESP Sorocaba
├── main_cli.py               # Launcher em modo Linha de Comando (Console)
├── main_gui.py               # Launcher em modo Interface Gráfica
└── requirements.txt          # Dependências do Python
```

---

## 🚀 Requisitos e Configuração

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```
*Para utilizar o pipeline de áudio MABI local, instale também:*
```bash
pip install nemo_toolkit[asr] librosa torch
```

### 2. Configurar Variáveis de Ambiente
Copie o exemplo de configuração e insira as suas chaves de API:
```bash
cp .env.example .env
```

### 3. Rodar a Assistente

* **Modo Console (CLI):**
  ```bash
  python main_cli.py
  ```
* **Modo Interface Gráfica (GUI):**
  ```bash
  python main_gui.py
  ```
* **Daemon do Wake Word (Monitoramento de Microfone em background):**
  ```bash
  python scripts/mina_wakeword_daemon.py
  ```

---

## 💡 Como Funciona o Classificador MABI Local (MABI Intent Classifier)
Mina utiliza uma lógica de expressões regulares estruturadas no arquivo **[intent_classifier.py](file:///C:/Users/Aluno/Mina-a-Assistente-Virtual/src/utils/intent_classifier.py)**. 
Toda entrada do usuário é interceptada:
* Se você disser *"qual a sala do professor Eduardo?"* ou *"qual a aula de hoje?"*, a resposta é computada localmente consultando o banco SQLite **`academic.db`** alimentado pelo coletor oficial do portal.
* Se a frase não bater com o escopo acadêmico, o fluxo continua e a pergunta vai para a nuvem.

---

## 👨‍💻 Autores
Desenvolvido pela equipe do **G.E.R.A (Grupo de Eletrônica e Robótica Aplicada)** da **UNESP Sorocaba**.
* **Mina AI:** Isaac Andrade.
* **MABI Classifier Pipeline:** Brenda Biral Batista.

---

## 🤝 Créditos e Agradecimentos

Este projeto é uma adaptação e extensão do **[py-xiaozhi](https://github.com/c2er/py-xiaozhi)**, um cliente de código aberto para o assistente de voz Xiaozhi AI. Agradecemos aos desenvolvedores originais pelo excelente trabalho que serviu de base tecnológica para o desenvolvimento da Mina.
