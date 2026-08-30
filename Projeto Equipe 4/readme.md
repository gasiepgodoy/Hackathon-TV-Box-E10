# Gateway IoT universal — TV box

## Introdução

A maioria dos ambientes com sensores acumula, com o tempo, uma mistura de
protocolos: um sensor industrial fala Modbus, outro fala OPC UA, um novo
módulo Wi-Fi fala MQTT, e cada um chega com seu próprio software de
monitoramento, sua própria tela, seu próprio banco de dados. Esse projeto
nasceu para resolver esse problema na raiz: um único gateway, rodando numa
TV box comum, que fala com qualquer protocolo de sensor e entrega tudo
num único dashboard, com um único histórico organizado.

## Objetivo

Construir um gateway IoT **verdadeiramente universal** — não apenas
suportando dois ou três protocolos fixos, mas com uma arquitetura de
adapters plugáveis onde adicionar um protocolo novo (Modbus, BLE, CoAP,
o que for) não exige tocar em nenhuma outra parte do sistema. A partir
disso, o gateway se propõe a:

- Traduzir qualquer protocolo de sensor para um formato normalizado único;
- Armazenar o histórico de forma organizada e consultável no InfluxDB,
  diferenciando cada sensor sem precisar de arquivos separados;
- Exibir tudo em tempo real num dashboard web, com gráficos, exportação
  em CSV e cadastro de sensores independente do protocolo;
- Ir além da simples visualização: analisar estatisticamente a saúde de
  cada sensor, detectar anomalias por múltiplos métodos complementares, e
  prever a tendência de curto prazo com banda de confiança — tudo rodando
  na própria borda, em hardware de baixo custo (TV box, ARM, poucos GB de
  RAM), sem depender de nuvem.

## O que diferencia este projeto

A maior parte dos gateways multiprotocolo se limita a dois ou três
protocolos embutidos diretamente no núcleo do sistema — adicionar um
protocolo novo significa reescrever o core. Aqui, o "core" (InfluxDB,
WebSocket, dashboard) nunca sabe de qual protocolo um dado veio: cada
adapter (`backend/app/adapters/`) apenas traduz seu protocolo específico
para um formato comum (`Leitura`) antes de entregá-lo ao resto do
sistema. Ver a seção *"Adicionando um novo protocolo"* mais abaixo.

Além disso, a camada de **análise** (estatística descritiva, detecção de
anomalias por múltiplos métodos, e previsão com banda de confiança) roda
inteiramente na borda, calibrada e validada empiricamente contra falsos
positivos — inclusive com hardware real (ESP32 via MQTT), não só dados
sintéticos. Essas seções estão detalhadas mais abaixo neste documento.

## Arquitetura

Gateway que recebe dados de sensores em qualquer protocolo (MQTT, OPC UA,
HTTP, e o que você adicionar depois), grava no InfluxDB e mostra tudo em
um dashboard em tempo real via WebSocket.

```
iot-gateway/
├── backend/     -> API Python (FastAPI) + adapters de protocolo + escrita no InfluxDB + análise
├── frontend/    -> Dashboard estático (HTML/CSS/JS puro, sem build step)
├── nginx/       -> Configs de exemplo para servir tudo na TV box
└── esp32/       -> Firmware de teste para validar o gateway com hardware real
```

---

## 1. Instalar o InfluxDB (na própria TV box ou em outra máquina da rede)

```bash
# Ubuntu/Debian (adapte se a TV box rodar outra distro)
mkdir -p /etc/apt/keyrings

# Baixa a chave oficial e confirma o fingerprint antes de confiar nela
curl --silent --location -O https://repos.influxdata.com/influxdata-archive.key
gpg --show-keys --with-fingerprint --with-colons ./influxdata-archive.key 2>&1 \
  | grep -q '^fpr:\+24C975CBA61A024EE1B631787C3D57159FC2F927:$' \
  && cat influxdata-archive.key \
  | gpg --dearmor \
  | sudo tee /etc/apt/keyrings/influxdata-archive.gpg > /dev/null \
  && echo 'deb [signed-by=/etc/apt/keyrings/influxdata-archive.gpg] https://repos.influxdata.com/debian stable main' \
  | sudo tee /etc/apt/sources.list.d/influxdata.list

sudo apt-get update && sudo apt-get install influxdb2 -y
sudo systemctl enable --now influxdb
```

> O comando antigo com `apt-key` foi descontinuado nas versões recentes do
> Ubuntu/Debian. O método acima é o atual: a chave GPG fica em
> `/etc/apt/keyrings/` e é referenciada explicitamente com `signed-by` no
> arquivo do repositório. O `grep` no meio confere o fingerprint da chave
> antes de usá-la — se ele não bater, o comando para e nada é instalado
> (proteção extra contra uma chave adulterada).

Depois acesse `http://<ip-da-tvbox>:8086`, crie a organização e o bucket
(ex: org `minha_org`, bucket `sensores`) pela UI de setup inicial, e gere
um **token de API** com permissão de leitura/escrita nesse bucket. Você
vai usar esses três valores no `.env` do backend.

## 2. Configurar e rodar o backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edite .env com INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Teste rápido: `curl http://localhost:8000/api/saude` deve responder `{"status":"ok"}`.

Para deixar rodando permanentemente na TV box, use o `nginx/gateway-backend.service`
como referência (copie para `/etc/systemd/system/`, ajuste os caminhos e usuário,
depois `systemctl enable --now gateway-backend`).

## 3. Testar sem sensores físicos

Antes de mexer com hardware real, cadastre um sensor com protocolo
**"Simulado"** na tela de Sensores — ele gera valores sozinho a cada
alguns segundos, o que já é suficiente para ver o dado chegando no
InfluxDB, no WebSocket e no gráfico do dashboard.

## 4. Publicar o frontend com Nginx

```bash
sudo mkdir -p /var/www/gateway-iot
sudo cp -r frontend /var/www/gateway-iot/frontend
sudo cp nginx/gateway.conf /etc/nginx/sites-available/gateway
sudo ln -s /etc/nginx/sites-available/gateway /etc/nginx/sites-enabled/gateway
sudo nginx -t && sudo systemctl reload nginx
```

Acesse `http://<ip-da-tvbox>/` — o Nginx serve o dashboard estático e
faz proxy de `/api/*` e `/ws` para o backend Python na porta 8000.

Se o backend rodar em outra máquina/porta, edite `frontend/js/common.js`
e defina `window.API_BASE` antes dele carregar, ou ajuste o proxy no
`gateway.conf`.

## 5. Cadastrando sensores reais

Na tela **Sensores**, clique em "Adicionar sensor" e escolha o protocolo:

- **MQTT**: informe o endereço/porta do broker e o tópico. Se o payload
  publicado for um número puro (`23.5`), funciona direto. Se for JSON
  (`{"valor": 23.5, "unidade": "C"}`), o campo "Campo do valor" diz qual
  chave ler.
- **OPC UA**: informe o `endpoint_url` do servidor e o `node_id` da
  variável que você quer monitorar (o gateway assina o node e recebe as
  mudanças automaticamente, sem polling).

O campo **Tipo** vira o *measurement* no InfluxDB — sensores do mesmo
tipo (ex: vários sensores `temperatura`) podem ser comparados/filtrados
juntos nas consultas, mesmo sendo instâncias diferentes.

## Como os dados ficam organizados no InfluxDB

Em vez de um arquivo por sensor, cada leitura vira um ponto assim:

```
measurement: temperatura          (= o "tipo" do sensor)
tags:        sensor_id=<uuid>, protocolo=mqtt, local=galpao_a
field:       valor=23.5
time:        <timestamp da leitura>
```

Isso permite tanto consultar um sensor isolado (`sensor_id == "..."`)
quanto todos os sensores de um tipo (`_measurement == "temperatura"`),
sem duplicar nada e sem precisar gerenciar arquivos manualmente.

## Adicionando um novo protocolo

1. Crie `backend/app/adapters/seu_protocolo_adapter.py` implementando
   `AdapterBase` (veja `mqtt_adapter.py` como referência mais simples).
2. Registre a classe em `ADAPTERS` no `backend/app/adapters/manager.py`.
3. Adicione a opção no `<select id="campo-protocolo">` e o bloco de
   config correspondente em `frontend/sensores.html` + `frontend/js/sensores.js`.

Nenhuma outra parte do sistema (InfluxDB, WebSocket, dashboard) precisa
mudar — todos trabalham em cima da `Leitura` já normalizada.

## Análise estatística e saúde dos sensores

A aba **Análise** do dashboard roda, por sensor e sob demanda, um conjunto
de métodos estatísticos que vão além de média e desvio padrão. A escolha
dos métodos não é arbitrária: cada um detecta um modo de falha diferente.

### Estatística descritiva e inferência

- Média, mediana, desvio padrão, amplitude, percentis, IQR
- **MAD** (desvio absoluto mediano) — medida de dispersão robusta, que não
  é distorcida por picos isolados como o desvio padrão é
- Assimetria e curtose — descrevem a forma da distribuição
- **Intervalo de confiança pela t de Student** — usamos t em vez de normal
  porque o desvio populacional é sempre desconhecido aqui; com amostra
  pequena a t dá um intervalo honestamente mais largo

### Forma da distribuição

Ajusta **Normal**, **Laplace** e **Cauchy** aos dados e escolhe a melhor
por AIC + teste de Kolmogorov-Smirnov. Isso não é enfeite: o resultado
decide qual detector de anomalia é válido.

- **Normal** → ruído bem-comportado, limiares por desvio padrão funcionam
- **Laplace** → caudas pesadas, picos ocasionais são normais para o sensor;
  a detecção passa a usar mediana/MAD
- **Cauchy** → caudas muito pesadas, sinal de instrumentação instável

Um teste de normalidade (Shapiro-Wilk / D'Agostino-Pearson) roda antes e
define automaticamente se o z-score clássico ou o robusto é o método
principal daquele sensor.

### Detectores de anomalia

Cada detector encontra um tipo distinto de problema — por isso rodamos
todos e cruzamos os resultados:

| Detector | Detecta |
|---|---|
| Z-score | Picos, quando os dados são normais |
| Z-score robusto (MAD) | Picos, quando há caudas pesadas |
| Cercas de Tukey (IQR) | Outliers sem supor distribuição nenhuma |
| Carta EWMA | Deslocamento pequeno e persistente da média |
| CUSUM | Drift sustentado (descalibração lenta) |
| Page-Hinkley | Momento exato da mudança de regime |
| Taxa de variação | Saltos fisicamente impossíveis entre leituras |
| Flatline | Sensor congelado repetindo o mesmo valor |

Um ponto marcado por dois ou mais detectores independentes é classificado
como **alta confiança** — bem mais confiável que um marcado por um só,
que pode ser artefato do método.

Os limiares de CUSUM e Page-Hinkley foram calibrados empiricamente contra
ruído branco puro. Os valores clássicos da literatura (h=5) pressupõem
monitoramento sequencial com reinício e disparavam em ~40% das séries
saudáveis quando aplicados a um lote inteiro; os valores atuais zeram os
falsos positivos sem perder sensibilidade a drift real, inclusive sutil.

### Regularidade de entrega (Poisson)

Poisson não se aplica ao *valor* lido (temperatura não é contagem), mas
se aplica perfeitamente à **contagem de leituras por intervalo**. Isso
detecta um modo de falha que nenhuma análise do valor pega: o sensor está
online e reportando valores plausíveis, mas entregando menos leituras que
deveria — perda de pacotes, rede instável ou firmware travando.

O índice de dispersão (variância/média dos intervalos) distingue chegada
regular de chegada em rajadas.

> Para MQTT e OPC UA o gateway não assume intervalo esperado, porque quem
> decide quando publicar é o dispositivo. Sem isso, o teste acusaria
> "perda de leituras" em sensores perfeitamente saudáveis.

### Pontuação de saúde

Combina todos os sinais numa nota de 0 a 100, com problemas descontando
pontos conforme a gravidade, e traduz cada problema encontrado numa ação
concreta ("agende recalibração", "verifique aterramento e blindagem").

**Sobre o escopo desta análise:** é um sistema baseado em regras
estatísticas, não um modelo preditivo treinado. Ele caracteriza com rigor
o estado atual e recente do sensor (drift, ruído, entrega, travamento) e
sinaliza tendências. Ele **não** prevê data de falha futura — isso exigiria
histórico de falhas reais rotulado, que um gateway recém-instalado não tem.

### Endpoints

```
GET /api/analise                      -> panorama de saúde de todos os sensores
GET /api/analise/{sensor_id}          -> análise completa de um sensor
GET /api/analise/{sensor_id}/saude    -> só o diagnóstico (mais leve)
```

Todos aceitam `?inicio=-24h&fim=...` (ISO-8601 ou duração relativa do Flux).
O resultado fica em cache por 30s para não recomputar tudo a cada clique.

## Previsão com banda de confiança (ARIMA)

A aba **Análise** tem um bloco de previsão que ajusta um modelo de série
temporal e entrega duas coisas diferentes:

**1. Projeção futura** — para onde o sensor está indo nos próximos passos,
com uma faixa de incerteza. Se o sensor tiver limites operacionais
cadastrados, o sistema avisa que o valor **deve** cruzar o limite e em
quantas leituras — em vez de avisar depois que já cruzou.

**2. Backtest na série observada** — o modelo estima onde cada ponto
deveria estar dado o comportamento anterior, e marcamos onde o valor real
caiu fora da banda. Isso é uma detecção de anomalia mais forte que os
limiares do módulo estatístico, porque considera tendência e
autocorrelação: numa série que sobe toda manhã, 26 °C às 14h pode ser
normal e 26 °C às 3h ser anômalo — um limiar fixo não distingue os dois.

### Escolha do modelo

Testa uma grade pequena de ordens ARIMA e escolhe pelo AIC. Se a série for
curta ou o ajuste falhar, cai para suavização exponencial de Holt, e em
último caso para uma banda baseada na variação recente. A ideia é sempre
devolver algo útil e sinalizar a limitação, em vez de falhar.

A grade é deliberadamente pequena e a série é subamostrada acima de 1500
pontos: ajustar ARIMA numa CPU de borda custa segundos, não milissegundos.
Por isso a previsão fica num endpoint separado (carregada sob demanda com
um botão) e o resultado é cacheado — a página principal não trava
esperando o modelo.

### Limites operacionais

No cadastro do sensor há dois campos opcionais, **limite mínimo** e
**limite máximo**. Quando preenchidos, aparecem no gráfico como linhas
tracejadas e habilitam o alerta preditivo. O alerta distingue:

- **provável** — a própria linha central da previsão cruza o limite
- **possível** — só a borda da banda de confiança cruza

### Endpoint

```
GET /api/analise/{sensor_id}/previsao?inicio=-24h&passos=12&confianca=0.95
```

### Sobre a escolha de ARIMA em vez de foundation model

Modelos de fundação para série temporal (Chronos, TimesFM, MOMENT) são
mais poderosos, mas exigem PyTorch: ~2 GB de disco e algumas centenas de
MB de RAM só para o runtime. Numa TV box com 2 GB de RAM dividida com
InfluxDB, backend e sistema, isso é pedir para o OOM killer derrubar um
serviço no meio da operação.

O ARIMA entrega o que este caso de uso realmente precisa — previsão de
curto prazo com banda de confiança calibrada — rodando em cerca de um
segundo e sem dependência pesada. Se um dia quiser a camada de foundation
model, o caminho de menor risco é rodá-la **fora** do gateway, num serviço
que consulta o InfluxDB pela rede, mantendo a borda leve.

### Autocorrelação: por que os detectores clássicos precisaram de ajuste

CUSUM, EWMA e Page-Hinkley vêm do controle estatístico de processo e
pressupõem **leituras independentes**. Grandezas físicas não são: a
temperatura de agora é quase a de um segundo atrás. Medindo a
autocorrelação de lag 1, ruído branco dá ~0 e uma série de sensor real
dá ~0,99.

Nesse regime, esses detectores disparam sozinhos. Numa série de passeio
aleatório sem nenhum defeito, o CUSUM aplicado aos valores brutos chegou
a marcar **297 de 300 pontos** — o que aparecia no diagnóstico como
"perda de calibração" em todo sensor saudável.

Duas correções foram aplicadas:

1. **Detectores sobre resíduos.** Quando a autocorrelação passa de 0,4, os
   detectores passam a operar sobre os resíduos de um AR(1) — o que sobra
   depois de descontar a dependência do valor anterior. Ali "anômalo"
   recupera o sentido correto: o valor deu um salto que não era previsível
   a partir da leitura anterior, em vez de apenas estar longe da mediana
   global.

2. **Teste de drift dedicado.** A pergunta "existe desvio sustentado?"
   passou a ser respondida por um teste próprio, que escolhe o método
   conforme a natureza da série: se ela tem raiz unitária, drift é a média
   das diferenças ser diferente de zero; se é estacionária em torno de uma
   tendência, drift é a inclinação da regressão ser significativa. Em
   ambos os casos os erros-padrão são corrigidos por HAC (Newey-West).

Também condicionamos a comparação entre janelas e o ajuste de distribuição
à série ter média estável — numa série que passeia, as duas metades
diferem por construção, e ajustar uma distribuição fixa descreve o passeio,
não o ruído do sensor.

**Limitação honesta:** num passeio aleatório puro, distinguir "drift real"
de "vagar aleatório" é estatisticamente difícil por natureza. Tendência
real em série estacionária é detectada de forma confiável (100% nos
testes); drift somado a um passeio é detectado com menos frequência. Isso
é uma propriedade do problema, não da implementação.
