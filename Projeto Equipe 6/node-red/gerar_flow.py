#!/usr/bin/env python3
"""Gera o flow do Node-RED para o dashboard do hub."""
import hashlib
import json
import pathlib

def nid(nome: str) -> str:
    return hashlib.md5(nome.encode()).hexdigest()[:16]

N = []          # nos do flow
def add(**kw):
    N.append(kw)
    return kw["id"]

# ----------------------------------------------------------------- config
add(id=nid("cfg-db"), type="sqlitedb", db="/var/lib/hub/dados.db",
    mode="RWC", name="hub — dados.db")

add(id=nid("cfg-mqtt"), type="mqtt-broker", name="mosquitto da box",
    broker="localhost", port="1883", clientid="node-red-hub",
    autoConnect=True, usetls=False, protocolVersion="4", keepalive="60",
    cleansession=True, autoUnsubscribe=True,
    birthTopic="", birthQos="0", birthPayload="", birthMsg={},
    closeTopic="", closeQos="0", closePayload="", closeMsg={},
    willTopic="", willQos="0", willPayload="", willMsg={},
    userProps="", sessionExpiry="")

# ------------------------------------------------------------------- abas
for i, (slug, nome, icone) in enumerate([
        ("tab-geral", "Visão Geral", "dashboard"),
        ("tab-hist",  "Histórico",   "show_chart"),
        ("tab-teste", "Testes",      "build")], 1):
    add(id=nid(slug), type="ui_tab", name=nome, icon=icone, order=i,
        disabled=False, hidden=False)

def grupo(slug, nome, aba, ordem, largura=6):
    add(id=nid(slug), type="ui_group", name=nome, tab=nid(aba), order=ordem,
        disp=True, width=str(largura), collapse=False, className="")

grupo("grp-estado",  "Estado do hub",            "tab-geral", 1, 6)
grupo("grp-agora",   "Sensor selecionado",       "tab-geral", 2, 6)
grupo("grp-ultimas", "Últimas leituras",         "tab-geral", 3, 12)
grupo("grp-fila",    "Fila de envio (pendente)", "tab-geral", 4, 12)
grupo("grp-export",  "Levar os dados",           "tab-geral", 5, 12)

grupo("grp-hctl",  "Período",           "tab-hist", 1, 12)
grupo("grp-htemp", "Temperatura",       "tab-hist", 2, 12)
grupo("grp-humid", "Umidade",           "tab-hist", 3, 6)
grupo("grp-hpres", "Pressão (só LoRa)", "tab-hist", 4, 6)

grupo("grp-inj",  "Injetar mensagens no MQTT", "tab-teste", 1, 6)
grupo("grp-diag", "Diagnóstico",               "tab-teste", 2, 6)
grupo("grp-traf", "Tráfego MQTT ao vivo",      "tab-teste", 3, 12)

# ------------------------------------------------------------- aba do flow
FLOW = nid("flow-hub")
add(id=FLOW, type="tab", label="Hub — Dashboard", disabled=False,
    info="Dashboard do hub de sensores da TV Box.\n\n"
         "Leituras vêm do SQLite em /var/lib/hub/dados.db; os testes publicam\n"
         "no Mosquitto local e atravessam o coletor de verdade.")

def fn(slug, nome, codigo, x, y, wires, outputs=1):
    return add(id=nid(slug), type="function", z=FLOW, name=nome, func=codigo,
               outputs=outputs, timeout=0, noerr=0, initialize="", finalize="",
               libs=[], x=x, y=y, wires=wires)

def sql(slug, nome, consulta, modo, x, y, wires):
    return add(id=nid(slug), type="sqlite", z=FLOW, mydb=nid("cfg-db"),
               sqlquery=modo, sql=consulta, name=nome, x=x, y=y, wires=wires)

def texto(slug, grp, ordem, rotulo, x, y, formato="{{msg.payload}}", largura=0):
    return add(id=nid(slug), type="ui_text", z=FLOW, group=nid(grp),
               order=ordem, width=largura, height=0, name="", label=rotulo,
               format=formato, layout="row-spread", className="", x=x, y=y,
               wires=[])

def modelo(slug, grp, nome, ordem, html, altura, x, y, largura=0):
    return add(id=nid(slug), type="ui_template", z=FLOW, group=nid(grp),
               name=nome, order=ordem, width=largura, height=altura,
               format=html, storeOutMessages=True, fwdInMessages=True,
               resendOnRefresh=True, templateScope="local", className="",
               x=x, y=y, wires=[[]])

COR = "<span style=\"color:{{msg.cor}}\">{{msg.payload}}</span>"

# =====================================================================
# 1. ESTADO — contagens gerais, atualizadas a cada 10 s
# =====================================================================
add(id=nid("tick10"), type="inject", z=FLOW, name="a cada 10 s",
    props=[{"p": "payload"}], repeat="10", crontab="", once=True,
    onceDelay="1", topic="", payload="", payloadType="date", x=130, y=100,
    wires=[[nid("q-estado"), nid("q-ultimas"), nid("q-fila"),
            nid("q-sensores"), nid("fn-qagora")]])

sql("q-estado", "contagens", """
SELECT (SELECT COUNT(*) FROM sensores)                          AS sensores,
       (SELECT COUNT(*) FROM sensores WHERE transporte='zigbee') AS zigbee,
       (SELECT COUNT(*) FROM sensores WHERE transporte='lora')   AS lora,
       (SELECT COUNT(*) FROM leituras)                          AS leituras,
       (SELECT COUNT(*) FROM agregados WHERE enviado=0)         AS ag_pend,
       (SELECT COUNT(*) FROM eventos   WHERE enviado=0)         AS ev_pend,
       (SELECT MAX(ts) FROM leituras)                           AS ultimo_ts
""".strip(), "fixed", 330, 60, [[nid("fn-estado")]])

fn("fn-estado", "espalhar estado", r"""
const r = (msg.payload || [])[0] || {};
const agora = Math.floor(Date.now() / 1000);

let idade = "sem leituras";
let cor = "#9e9e9e";

if (r.ultimo_ts) {
    const s = agora - r.ultimo_ts;
    idade = s < 90    ? s + " s atrás"
          : s < 5400  ? Math.round(s / 60) + " min atrás"
          :             (s / 3600).toFixed(1) + " h atrás";

    /* O coletor só descarrega o buffer a cada intervalo_flush_s (300 s por
     * padrão). Um atraso abaixo disso é o funcionamento normal, não uma
     * falha — por isso o verde vai até 10 min, e não até 1 min. */
    cor = s < 600 ? "#8bc34a" : s < 3600 ? "#ffb300" : "#e53935";
}

const fila = (r.ag_pend || 0) + (r.ev_pend || 0);
const plural = (n, um, muitos) => n + " " + (n === 1 ? um : muitos);

return [
    { payload: (r.sensores || 0) + "  (" + (r.zigbee || 0) + " zigbee / "
               + (r.lora || 0) + " lora)", cor: "#e0e0e0" },
    { payload: (r.leituras || 0).toLocaleString("pt-BR"), cor: "#e0e0e0" },
    { payload: plural(r.ag_pend || 0, "agregado", "agregados") + " · "
               + plural(r.ev_pend || 0, "evento", "eventos"),
      cor: fila > 0 ? "#ffb300" : "#8bc34a" },
    { payload: idade, cor: cor }
];
""".strip(), 520, 60,
   [[nid("txt-sensores")], [nid("txt-leituras")],
    [nid("txt-pend")], [nid("txt-idade")]], outputs=4)

texto("txt-sensores", "grp-estado", 1, "Sensores",      760, 20,  COR)
texto("txt-leituras", "grp-estado", 2, "Leituras",      760, 60,  COR)
texto("txt-pend",     "grp-estado", 3, "Aguardando envio", 760, 100, COR)
texto("txt-idade",    "grp-estado", 4, "Última leitura", 760, 140, COR)

# =====================================================================
# 2. ÚLTIMAS LEITURAS
# =====================================================================
sql("q-ultimas", "últimas leituras",
    "SELECT * FROM v_ultimas_leituras LIMIT 15",
    "fixed", 340, 200, [[nid("fn-ultimas")]])

fn("fn-ultimas", "formatar", r"""
// Números crus ficam ilegíveis na tabela (22.399999). Formatamos aqui, e não
// no SQL, para o gráfico continuar recebendo os valores originais.
const n = (v, casas) => (v === null || v === undefined) ? "—" : v.toFixed(casas);

msg.payload = (msg.payload || []).map(l => ({
    sensor: l.sensor,
    origem: l.origem,
    quando: l.quando,
    temperatura: n(l.temperatura, 1),
    umidade: n(l.umidade, 1),
    pressao: n(l.pressao, 1),
    bateria: l.bateria === null ? "—" : l.bateria + "%",
    // Zigbee reporta LQI (0-255, maior é melhor); LoRa reporta RSSI em dBm
    // (negativo). Mostrar só o número confundiria as duas escalas.
    sinal: l.linkquality === null ? "—"
         : (l.origem === "lora" ? l.linkquality + " dBm" : "LQI " + l.linkquality)
}));
return msg;
""".strip(), 520, 200, [[nid("tbl-ultimas")]])

TABELA_CSS = """
<style>
.hub-tab { width:100%; border-collapse:collapse; font-size:12px; }
.hub-tab th { text-align:left; padding:5px 4px; border-bottom:1px solid #888;
              font-weight:600; text-transform:uppercase; font-size:11px;
              opacity:.75; }
.hub-tab td { padding:5px 4px; border-bottom:1px solid rgba(128,128,128,.2); }
.hub-tab tr:hover td { background:rgba(128,128,128,.08); }
.hub-vazio { padding:12px; opacity:.6; font-style:italic; }
.org-lora   { color:#4fc3f7; font-weight:600; }
.org-zigbee { color:#aed581; font-weight:600; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
</style>
"""

modelo("tbl-ultimas", "grp-ultimas", "tabela de leituras", 1, TABELA_CSS + """
<table class="hub-tab">
  <tr>
    <th>Sensor</th><th>Origem</th><th>Quando</th>
    <th class="num">°C</th><th class="num">% UR</th><th class="num">hPa</th>
    <th class="num">Bateria</th><th class="num">Sinal</th>
  </tr>
  <tr ng-repeat="l in msg.payload track by $index">
    <td>{{l.sensor}}</td>
    <td><span class="org-{{l.origem}}">{{l.origem}}</span></td>
    <td>{{l.quando}}</td>
    <td class="num">{{l.temperatura}}</td>
    <td class="num">{{l.umidade}}</td>
    <td class="num">{{l.pressao}}</td>
    <td class="num">{{l.bateria}}</td>
    <td class="num">{{l.sinal}}</td>
  </tr>
</table>
<div class="hub-vazio" ng-if="!msg.payload || msg.payload.length === 0">
  Nenhuma leitura no banco. O serviço hub-coletor está rodando?
  <br>Use a aba <b>Testes</b> para injetar uma leitura e conferir o caminho.
</div>
""", 8, 760, 200, largura=0)

# =====================================================================
# 3. FILA DE ENVIO
# =====================================================================
sql("q-fila", "pendentes", """
SELECT 'evento' AS tipo,
       COALESCE(s.nome, s.ieee, '—')                     AS sensor,
       e.tipo                                            AS descricao,
       ROUND(e.valor, 1)                                 AS valor,
       datetime(e.ts, 'unixepoch', 'localtime')          AS quando,
       e.prioridade                                      AS prioridade
FROM eventos e LEFT JOIN sensores s ON s.id = e.sensor_id
WHERE e.enviado = 0
UNION ALL
SELECT 'agregado',
       COALESCE(s.nome, s.ieee),
       a.amostras || ' amostras',
       ROUND(a.temp_media, 1),
       datetime(a.inicio, 'unixepoch', 'localtime'),
       0
FROM agregados a JOIN sensores s ON s.id = a.sensor_id
WHERE a.enviado = 0
ORDER BY prioridade DESC, quando DESC
LIMIT 20
""".strip(), "fixed", 340, 280, [[nid("fn-fila")]])

fn("fn-fila", "formatar fila", r"""
/* A ordem aqui espelha a do enviador: eventos primeiro (por prioridade),
 * agregados depois. Se o enlace só couber alguns pacotes, é isso que sobe. */
msg.payload = (msg.payload || []).map(r => ({
    tipo: r.tipo,
    sensor: r.sensor,
    descricao: r.descricao,
    valor: r.valor === null ? "—" : r.valor,
    quando: r.quando,
    prioridade: r.tipo === "evento" ? r.prioridade : "—"
}));
return msg;
""".strip(), 520, 280, [[nid("tbl-fila")]])

modelo("tbl-fila", "grp-fila", "tabela da fila", 1, TABELA_CSS + """
<table class="hub-tab">
  <tr>
    <th>Tipo</th><th>Sensor</th><th>Descrição</th>
    <th class="num">Valor</th><th>Quando</th><th class="num">Prior.</th>
  </tr>
  <tr ng-repeat="r in msg.payload track by $index">
    <td><span ng-style="{color: r.tipo === 'evento' ? '#ff8a65' : '#90a4ae'}">
        {{r.tipo}}</span></td>
    <td>{{r.sensor}}</td>
    <td>{{r.descricao}}</td>
    <td class="num">{{r.valor}}</td>
    <td>{{r.quando}}</td>
    <td class="num">{{r.prioridade}}</td>
  </tr>
</table>
<div class="hub-vazio" ng-if="!msg.payload || msg.payload.length === 0">
  Fila vazia — tudo que foi agregado já subiu.
</div>
""", 6, 760, 280)

# ------------------------------------------------- atalho para o exportador
# O endereco e montado em JavaScript a partir do host do proprio dashboard, e
# nao fixado em 192.168.4.1: quem abre o painel pelo AP, pela rede cabeada ou
# pela VPN recebe um link que funciona na rede em que ja esta. O exportador roda
# sempre na mesma maquina que o Node-RED, so em outra porta.
modelo("lnk-export", "grp-export", "atalho para o exportador", 1, """
<div style="padding:6px 2px; line-height:1.7">
  <a id="hub-lnk-export" href="#" target="_blank"
     style="color:#7BEC5A; font-weight:600; text-decoration:none">
     Abrir a página de exportação ↗</a>
  <div style="font-size:12px; color:#9BAA9C">
    Baixar CSV (só agregados ou tudo) ou o banco inteiro — sem instalar nada.
  </div>
</div>
<script>
(function () {
  var a = document.getElementById("hub-lnk-export");
  if (a) { a.href = "http://" + window.location.hostname + ":8000/"; }
})();
</script>
""", 2, 760, 340)

# =====================================================================
# 4. SENSOR SELECIONADO — dropdown + medidores
# =====================================================================
sql("q-sensores", "lista de sensores",
    "SELECT ieee, COALESCE(nome, ieee) AS rotulo, transporte "
    "FROM sensores ORDER BY rotulo",
    "fixed", 340, 380, [[nid("fn-opcoes")]])

fn("fn-opcoes", "montar opções", r"""
/* O dropdown é repovoado a cada 10 s: sensores novos aparecem sozinhos,
 * inclusive os criados pelos botões de teste. */
const linhas = msg.payload || [];
msg.options = linhas.map(s => {
    const o = {};
    o[s.rotulo + "  (" + s.transporte + ")"] = s.ieee;
    return o;
});

/* Adota o primeiro sensor quando não há seleção, para a tela não nascer
 * vazia — e também quando o sensor selecionado deixou de existir (é o que
 * acontece ao apagar os sensores de teste). Sem esta segunda checagem a
 * seleção ficaria presa num ieee inexistente e os medidores congelariam. */
const atual = flow.get("sensor");
const existe = linhas.some(s => s.ieee === atual);
if (!existe) {
    flow.set("sensor", linhas.length ? linhas[0].ieee : null);
}
return msg;
""".strip(), 520, 380, [[nid("dd-sensor")]])

add(id=nid("dd-sensor"), type="ui_dropdown", z=FLOW, name="", label="Sensor",
    tooltip="", place="escolha um sensor", group=nid("grp-agora"), order=1,
    width=0, height=0, passthru=False, multiple=False, options=[],
    payload="", topic="topic", topicType="msg", className="",
    x=760, y=380, wires=[[nid("fn-sel")]])

fn("fn-sel", "guardar seleção", r"""
flow.set("sensor", msg.payload);
return msg;   // segue para atualizar medidores e gráficos na hora
""".strip(), 950, 380, [[nid("fn-qagora"), nid("fn-qhist")]])

fn("fn-qagora", "parâmetros", r"""
const ieee = flow.get("sensor");
if (!ieee) { return null; }        // ainda não há sensores no banco
msg.params = { $ieee: ieee };
return msg;
""".strip(), 330, 460, [[nid("q-agora")]])

sql("q-agora", "última leitura do sensor", """
SELECT l.ts, l.temperatura, l.umidade, l.pressao, l.bateria, l.linkquality,
       s.transporte, COALESCE(s.nome, s.ieee) AS rotulo
FROM leituras l JOIN sensores s ON s.id = l.sensor_id
WHERE s.ieee = $ieee
ORDER BY l.ts DESC LIMIT 1
""".strip(), "prepared", 530, 460, [[nid("fn-agora")]])

fn("fn-agora", "medidores", r"""
const r = (msg.payload || [])[0];
if (!r) {
    // Sensor cadastrado mas ainda sem leitura: zera em vez de manter na tela
    // o valor do sensor anterior, que seria lido como dado atual.
    return [{ payload: 0 }, { payload: 0 },
            { payload: "sem leitura", cor: "#9e9e9e" },
            { payload: "—", cor: "#9e9e9e" }];
}

const press = r.pressao === null
    ? "— (Zigbee não mede pressão)"
    : r.pressao.toFixed(1) + " hPa";

let sinal = "—";
if (r.linkquality !== null) {
    sinal = r.transporte === "lora"
        ? r.linkquality + " dBm (RSSI)"
        : "LQI " + r.linkquality + " / 255";
}
if (r.bateria !== null) { sinal += "  ·  bateria " + r.bateria + "%"; }

return [
    { payload: r.temperatura === null ? 0 : +r.temperatura.toFixed(1) },
    { payload: r.umidade === null ? 0 : +r.umidade.toFixed(1) },
    { payload: press, cor: r.pressao === null ? "#9e9e9e" : "#4fc3f7" },
    { payload: sinal, cor: "#e0e0e0" }
];
""".strip(), 730, 460,
   [[nid("g-temp")], [nid("g-umid")], [nid("txt-press")], [nid("txt-sinal")]],
   outputs=4)

add(id=nid("g-temp"), type="ui_gauge", z=FLOW, name="", group=nid("grp-agora"),
    order=2, width=3, height=3, gtype="gage", title="Temperatura", label="°C",
    format="{{value}}", min="-10", max="50",
    colors=["#00b7ff", "#00b500", "#ca3838"], seg1="3", seg2="35",
    diff=False, className="", x=950, y=420, wires=[])

add(id=nid("g-umid"), type="ui_gauge", z=FLOW, name="", group=nid("grp-agora"),
    order=3, width=3, height=3, gtype="gage", title="Umidade", label="% UR",
    format="{{value}}", min=0, max=100,
    colors=["#ca3838", "#00b500", "#00b7ff"], seg1="20", seg2="95",
    diff=False, className="", x=950, y=460, wires=[])

texto("txt-press", "grp-agora", 4, "Pressão", 950, 500, COR)
texto("txt-sinal", "grp-agora", 5, "Sinal",   950, 540, COR)

# =====================================================================
# 5. HISTÓRICO
# =====================================================================
add(id=nid("dd-periodo"), type="ui_dropdown", z=FLOW, name="",
    label="Período", tooltip="", place="", group=nid("grp-hctl"), order=1,
    width=0, height=0, passthru=False, multiple=False,
    options=[{"label": "Última hora", "value": "1h", "type": "str"},
             {"label": "6 horas",     "value": "6h", "type": "str"},
             {"label": "24 horas",    "value": "24h", "type": "str"},
             {"label": "7 dias",      "value": "7d", "type": "str"}],
    payload="", topic="topic", topicType="msg", className="",
    x=130, y=640, wires=[[nid("fn-periodo")]])

fn("fn-periodo", "guardar período", r"""
flow.set("periodo", msg.payload);
return msg;
""".strip(), 330, 640, [[nid("fn-qhist")]])

add(id=nid("tick30"), type="inject", z=FLOW, name="a cada 30 s",
    props=[{"p": "payload"}], repeat="30", crontab="", once=True,
    onceDelay="2", topic="", payload="", payloadType="date",
    x=130, y=700, wires=[[nid("fn-qhist")]])

fn("fn-qhist", "escolher fonte", r"""
const ieee = flow.get("sensor");
if (!ieee) { return null; }

const HORAS = { "1h": 1, "6h": 6, "24h": 24, "7d": 168 };
const periodo = flow.get("periodo") || "6h";
const horas = HORAS[periodo] || 6;

msg.params = { $ieee: ieee, $desde: Math.floor(Date.now() / 1000) - horas * 3600 };
msg.periodo = periodo;

/* Janelas curtas leem as leituras BRUTAS: é onde a resolução real importa,
 * e é o que prova que o coletor está gravando agora.
 * Janelas longas leem os AGREGADOS: 7 dias de leituras brutas seriam
 * milhares de pontos para o navegador desenhar, num aparelho de 1,8 GB. */
if (horas <= 6) {
    msg.modo = "bruto";
    return [msg, null];
}
msg.modo = "agregado";
return [null, msg];
""".strip(), 530, 660, [[nid("q-hbruto")], [nid("q-hagr")]], outputs=2)

sql("q-hbruto", "leituras brutas", """
SELECT l.ts AS t, l.temperatura, l.umidade, l.pressao
FROM leituras l JOIN sensores s ON s.id = l.sensor_id
WHERE s.ieee = $ieee AND l.ts >= $desde
ORDER BY l.ts
""".strip(), "prepared", 760, 620, [[nid("fn-chart")]])

sql("q-hagr", "agregados", """
SELECT a.inicio AS t, a.temp_min, a.temp_media, a.temp_max,
       a.umid_media, a.press_media
FROM agregados a JOIN sensores s ON s.id = a.sensor_id
WHERE a.inicio >= $desde
  AND a.sensor_id = (SELECT id FROM sensores WHERE ieee = $ieee)
ORDER BY a.inicio
""".strip(), "prepared", 760, 700, [[nid("fn-chart")]])

fn("fn-chart", "montar séries", r"""
const linhas = msg.payload || [];
const bruto = msg.modo === "bruto";

// Array vazio limpa o gráfico. Sem isso o Node-RED mantém a série anterior
// na tela e você leria dados do sensor errado depois de trocar no dropdown.
if (!linhas.length) {
    const vazio = { payload: [] };
    return [vazio, vazio, vazio];
}

const serie = campo => linhas
    .map(r => ({ x: r.t * 1000, y: r[campo] }))
    .filter(p => p.y !== null && p.y !== undefined);

const grafico = (nomes, campos) => {
    const dados = campos.map(serie);
    // Se nenhuma série tem ponto (ex.: pressão num sensor Zigbee), devolve
    // vazio para o gráfico mostrar "sem dados" em vez de eixos em branco.
    if (!dados.some(d => d.length)) { return { payload: [] }; }
    return { payload: [{ series: nomes, data: dados, labels: [""] }] };
};

if (bruto) {
    return [
        grafico(["temperatura"], ["temperatura"]),
        grafico(["umidade"], ["umidade"]),
        grafico(["pressão"], ["pressao"])
    ];
}

/* Nos agregados mostramos mín/média/máx juntos, e não só a média: uma geada
 * de 20 minutos desaparece numa média horária — é exatamente o evento que o
 * hub existe para detectar. */
return [
    grafico(["mín", "média", "máx"], ["temp_min", "temp_media", "temp_max"]),
    grafico(["umidade média"], ["umid_media"]),
    grafico(["pressão média"], ["press_media"])
];
""".strip(), 980, 660,
   [[nid("ch-temp")], [nid("ch-umid")], [nid("ch-press")]], outputs=3)

def grafico(slug, grp, rotulo, x, y, cores):
    add(id=nid(slug), type="ui_chart", z=FLOW, name="", group=nid(grp),
        order=1, width=0, height=0, label=rotulo, chartType="line",
        legend="true", xformat="HH:mm", interpolate="linear",
        nodata="sem dados no período", dot=False, ymin="", ymax="",
        removeOlder=1, removeOlderPoints="", removeOlderUnit="604800",
        cutout=0, useOneColor=False, useUTC=False, colors=cores, outputs=1,
        useDifferentColor=False, className="", x=x, y=y, wires=[[]])

grafico("ch-temp", "grp-htemp", "Temperatura (°C)", 1200, 620,
        ["#4fc3f7", "#ff9800", "#e53935", "#2ca02c", "#98df8a",
         "#d62728", "#ff9896", "#9467bd", "#c5b0d5"])
grafico("ch-umid", "grp-humid", "Umidade (% UR)", 1200, 660,
        ["#26a69a", "#aec7e8", "#ff7f0e", "#2ca02c", "#98df8a",
         "#d62728", "#ff9896", "#9467bd", "#c5b0d5"])
grafico("ch-press", "grp-hpres", "Pressão (hPa)", 1200, 700,
        ["#ab47bc", "#aec7e8", "#ff7f0e", "#2ca02c", "#98df8a",
         "#d62728", "#ff9896", "#9467bd", "#c5b0d5"])

# =====================================================================
# 6. TESTES — botões que publicam no MQTT de verdade
# =====================================================================
def botao(slug, grp, ordem, rotulo, carga, cor_fundo, destino, x, y, icone=""):
    add(id=nid(slug), type="ui_button", z=FLOW, name="", group=nid(grp),
        order=ordem, width=0, height=0, passthru=False, label=rotulo,
        tooltip="", color="", bgcolor=cor_fundo, className="", icon=icone,
        payload=carga, payloadType="str", topic="teste", topicType="str",
        x=x, y=y, wires=[[nid(destino)]])

botao("btn-zigbee",   "grp-inj", 1, "Leitura Zigbee normal",   "zigbee",
      "#558b2f", "fn-injetar", 130, 820)
botao("btn-lora",     "grp-inj", 2, "Uplink LoRa (BME280)",    "lora",
      "#0277bd", "fn-injetar", 130, 860)
botao("btn-geada",    "grp-inj", 3, "Simular geada (1.5 °C)",  "geada",
      "#00838f", "fn-injetar", 130, 900)
botao("btn-quebrado", "grp-inj", 4, "Nó LoRa com BME quebrado", "quebrado",
      "#ef6c00", "fn-injetar", 130, 940)
botao("btn-invalido", "grp-inj", 5, "Payload inválido",        "invalido",
      "#c62828", "fn-injetar", 130, 980)

fn("fn-injetar", "montar mensagem de teste", r"""
/* Os botões publicam no Mosquitto REAL da box. A mensagem percorre o mesmo
 * caminho de um sensor de verdade: mosquitto -> hub-coletor -> SQLite.
 * Não é uma simulação da interface; se aparecer na tabela, o caminho inteiro
 * está funcionando. */
const sorteio = (min, max) => +(min + Math.random() * (max - min)).toFixed(1);

// Envelope que o ChirpStack publica num uplink. O coletor decodifica o campo
// 'data' (base64) quando não há codec configurado no Device Profile.
function uplinkLoRa(nome, corpo) {
    return JSON.stringify({
        deviceInfo: { deviceName: nome, devEui: "e2192ce6b4deaf62",
                      applicationName: "hub" },
        devAddr: "00e8cdfb",
        fCnt: Math.floor(Date.now() / 1000) % 65536,
        fPort: 1,
        data: Buffer.from(corpo, "utf8").toString("base64"),
        rxInfo: [{ gatewayId: "teste000dashboard",
                   rssi: -90 - Math.round(Math.random() * 25), snr: 8.5 }],
        txInfo: { frequency: 916800000,
                  modulation: { lora: { spreadingFactor: 7, bandwidth: 125000 } } }
    });
}

switch (msg.payload) {
    case "zigbee":
        msg.topic = "zigbee2mqtt/teste_zigbee";
        msg.payload = JSON.stringify({
            temperature: sorteio(17, 31),
            humidity: sorteio(40, 85),
            battery: 87,
            linkquality: 120 + Math.round(Math.random() * 100)
        });
        msg.nota = "leitura Zigbee normal — deve aparecer na tabela";
        break;

    case "lora":
        // Mesmas chaves curtas que o firmware do nó envia de verdade.
        msg.topic = "application/1/device/e2192ce6b4deaf62/event/up";
        msg.payload = uplinkLoRa("teste_lora", JSON.stringify({
            t: sorteio(17, 31), h: sorteio(40, 85), p: sorteio(1005, 1020)
        }));
        msg.nota = "uplink LoRa com pressão — só esta origem preenche hPa";
        break;

    case "geada":
        /* Abaixo de temp_min (3.0 °C no hub.ini). O evento NÃO nasce agora:
         * quem o cria é o hub-ciclo, que roda periodicamente. Depois de
         * clicar, espere o ciclo (ou rode `hub-ciclo` na box) e veja o evento
         * surgir na Fila de envio. */
        msg.topic = "zigbee2mqtt/teste_geada";
        msg.payload = JSON.stringify({
            temperature: 1.5, humidity: 92, battery: 64, linkquality: 90
        });
        msg.nota = "temperatura de geada — evento aparece após o hub-ciclo";
        break;

    case "quebrado":
        msg.topic = "application/1/device/e2192ce6b4deaf62/event/up";
        msg.payload = uplinkLoRa("teste_lora", JSON.stringify({ err: "bme280" }));
        msg.nota = "nó vivo mas sem sensor — recusado, porém visível no tráfego";
        break;

    case "invalido":
        msg.topic = "zigbee2mqtt/teste_zigbee";
        msg.payload = "isto-nao-e-json";
        msg.nota = "payload inválido — deve ser recusado pelo coletor";
        break;

    default:
        return null;
}
return msg;
""".strip(), 400, 900, [[nid("mqtt-out")]])

add(id=nid("mqtt-out"), type="mqtt out", z=FLOW, name="publicar", topic="",
    qos="0", retain="", respTopic="", contentType="", userProps="", correl="",
    expiry="", broker=nid("cfg-mqtt"), x=700, y=900, wires=[])

# ---------------------------------------------------------- diagnóstico
botao("btn-diag", "grp-diag", 1, "Rodar diagnóstico", "diag", "#37474f",
      "q-diag", 130, 1060)

sql("q-diag", "checagens do banco", """
SELECT (SELECT COUNT(*) FROM sqlite_master WHERE type='table')            AS tabelas,
       (SELECT COUNT(*) FROM sqlite_master
         WHERE type='view' AND name='v_ultimas_leituras')                 AS tem_view,
       (SELECT journal_mode FROM pragma_journal_mode())                   AS journal,
       (SELECT page_count FROM pragma_page_count())                       AS paginas,
       (SELECT page_size  FROM pragma_page_size())                        AS tam_pagina,
       (SELECT COUNT(*) FROM pragma_table_info('leituras')
         WHERE name='pressao')                                            AS col_pressao,
       (SELECT COUNT(*) FROM pragma_table_info('sensores')
         WHERE name='transporte')                                         AS col_transporte,
       (SELECT COUNT(*) FROM pragma_table_info('agregados')
         WHERE name='press_media')                                        AS col_press_media,
       (SELECT MAX(ts) FROM leituras)                                     AS ultimo_ts,
       (SELECT COUNT(*) FROM leituras
         WHERE ts >= unixepoch() - 3600)                                  AS leituras_1h
""".strip(), "fixed", 360, 1060, [[nid("fn-diag")]])

fn("fn-diag", "montar relatório", r"""
const r = (msg.payload || [])[0] || {};
const linhas = [];
const ok  = (t, d) => linhas.push({ estado: "ok",    texto: t, detalhe: d });
const mau = (t, d) => linhas.push({ estado: "mau",   texto: t, detalhe: d });
const alerta = (t, d) => linhas.push({ estado: "alerta", texto: t, detalhe: d });

// 5 tabelas: sensores, leituras, agregados, eventos, meta (+ internas do SQLite)
if (r.tabelas >= 5) { ok("Tabelas do esquema", r.tabelas + " tabelas"); }
else { mau("Tabelas do esquema", "só " + (r.tabelas || 0)
           + " — caminho do banco errado? O modo RWC cria um arquivo vazio"
           + " em silêncio quando o caminho não existe."); }

r.tem_view ? ok("View v_ultimas_leituras", "presente")
           : mau("View v_ultimas_leituras", "ausente — rode o schema.sql");

/* As três colunas da integração LoRa. Bancos criados antes dela não são
 * recriados pelo schema.sql (tudo é IF NOT EXISTS); quem as acrescenta é
 * migrar() em src/hub/db.py. É o teste de que a migração rodou nesta box. */
const faltando = [];
if (!r.col_pressao)     { faltando.push("leituras.pressao"); }
if (!r.col_transporte)  { faltando.push("sensores.transporte"); }
if (!r.col_press_media) { faltando.push("agregados.press_media"); }
faltando.length
    ? mau("Migração LoRa", "faltam: " + faltando.join(", ")
          + " — rode migrar() de src/hub/db.py")
    : ok("Migração LoRa", "as 3 colunas existem");

r.journal === "wal"
    ? ok("journal_mode", "WAL (menos escrita no cartão SD)")
    : alerta("journal_mode", r.journal + " — esperado WAL");

if (r.paginas) {
    const mb = (r.paginas * r.tam_pagina / 1048576).toFixed(2);
    ok("Tamanho do banco", mb + " MB");
}

if (!r.ultimo_ts) {
    mau("Leituras", "banco sem nenhuma leitura");
} else {
    const s = Math.floor(Date.now() / 1000) - r.ultimo_ts;
    const desc = (r.leituras_1h || 0) + " na última hora · mais recente há "
               + (s < 90 ? s + " s" : Math.round(s / 60) + " min");
    // O coletor descarrega em lote a cada 5 min; 15 min de folga evita
    // acusar falha durante a operação normal.
    s < 900 ? ok("Leituras", desc) : alerta("Leituras", desc);
}

msg.payload = linhas;
msg.quando = new Date().toLocaleString("pt-BR");
return msg;
""".strip(), 560, 1060, [[nid("tpl-diag")]])

modelo("tpl-diag", "grp-diag", "relatório", 2, """
<style>
.diag { font-size:12px; line-height:1.5; }
.diag li { list-style:none; margin:0 0 6px 0; }
.diag .m { font-weight:600; }
.diag .d { opacity:.75; display:block; margin-left:20px; }
.diag .ok     { color:#8bc34a; }
.diag .alerta { color:#ffb300; }
.diag .mau    { color:#e53935; }
.diag .quando { opacity:.5; font-size:11px; margin-top:8px; }
</style>
<div class="diag">
  <ul>
    <li ng-repeat="l in msg.payload track by $index">
      <span class="m {{l.estado}}">
        {{ l.estado === 'ok' ? '✓' : (l.estado === 'alerta' ? '!' : '✗') }}
        {{l.texto}}
      </span>
      <span class="d">{{l.detalhe}}</span>
    </li>
  </ul>
  <div class="quando" ng-if="msg.quando">verificado em {{msg.quando}}</div>
  <div ng-if="!msg.payload">Clique em <b>Rodar diagnóstico</b>.</div>
</div>
""", 8, 780, 1060)

# --------------------------------------------------- limpar dados de teste
botao("btn-limpar", "grp-diag", 3, "Apagar sensores de teste", "limpar",
      "#6a1b9a", "fn-sql-limpar", 130, 1160)

fn("fn-sql-limpar", "SQL da limpeza", r"""
/* O SQL vai em msg.topic, e não no campo do nó: no modo "batch" o
 * node-red-node-sqlite executa msg.topic com db.exec() e IGNORA o campo SQL
 * (só os modos "fixed" e "prepared" usam o campo). Deixar a instrução lá
 * dentro faria o nó tentar executar "teste", o topic vindo do botão.
 *
 * Precisa ser batch porque são quatro instruções: db.all(), usado pelos
 * outros modos, roda apenas a primeira e descarta o resto sem erro.
 *
 * E os filhos são apagados na mão porque ON DELETE CASCADE só age com
 * PRAGMA foreign_keys = ON, que vale por CONEXÃO. O hub liga o pragma na
 * conexão dele; a do Node-RED é outra e nasce com ele desligado. Sem estes
 * DELETEs sobrariam leituras órfãs apontando para sensores inexistentes. */
const ALVO = "SELECT id FROM sensores WHERE ieee IN "
           + "('teste_zigbee','teste_lora','teste_geada')";

msg.topic = [
    "DELETE FROM leituras  WHERE sensor_id IN (" + ALVO + ");",
    "DELETE FROM agregados WHERE sensor_id IN (" + ALVO + ");",
    "DELETE FROM eventos   WHERE sensor_id IN (" + ALVO + ");",
    "DELETE FROM sensores  WHERE ieee IN "
        + "('teste_zigbee','teste_lora','teste_geada');"
].join("\n");
return msg;
""".strip(), 360, 1160, [[nid("q-limpar")]])

sql("q-limpar", "apagar teste_*", "", "batch", 600, 1160, [[nid("fn-limpou")]])

fn("fn-limpou", "confirmar", r"""
// A seleção some junto com o sensor; fn-opcoes escolhe outra no próximo tick.
flow.set("sensor", null);

msg.payload = [{ estado: "ok", texto: "Sensores de teste apagados",
                 detalhe: "teste_zigbee, teste_lora e teste_geada, com suas "
                        + "leituras, agregados e eventos" }];
msg.quando = new Date().toLocaleString("pt-BR");
return msg;
""".strip(), 800, 1160, [[nid("tpl-diag")]])

# ------------------------------------------------------- tráfego ao vivo
add(id=nid("mqtt-in-z"), type="mqtt in", z=FLOW, name="zigbee2mqtt/#",
    topic="zigbee2mqtt/#", qos="0", datatype="utf8", broker=nid("cfg-mqtt"),
    nl=False, rap=True, rh=0, inputs=0, x=140, y=1260,
    wires=[[nid("fn-trafego")]])

add(id=nid("mqtt-in-l"), type="mqtt in", z=FLOW, name="application/#",
    topic="application/#", qos="0", datatype="utf8", broker=nid("cfg-mqtt"),
    nl=False, rap=True, rh=0, inputs=0, x=140, y=1310,
    wires=[[nid("fn-trafego")]])

fn("fn-trafego", "classificar e acumular", r"""
/* ATENÇÃO: esta classificação é uma DICA, não a decisão real. Quem decide o
 * que entra no banco é diagnosticar() em src/hub/coletor.py, em Python — este
 * código é uma réplica simplificada e pode divergir dele com o tempo.
 * A comparação honesta é: apareceu aqui como "aceita" e NÃO apareceu na
 * tabela de leituras? Então o problema está no coletor, não no MQTT.
 * Para o veredito autoritativo use `python3 -m hub.cli espiar` na box. */
const MEDIDAS = ["temperature", "temperatura", "temp", "t",
                 "humidity", "umidade", "hum", "h",
                 "pressure", "pressao", "press", "p"];

const topico = msg.topic || "";
let texto = msg.payload;
if (Buffer.isBuffer(texto)) { texto = texto.toString("utf8"); }
if (typeof texto !== "string") { texto = JSON.stringify(texto); }

let estado = "aceita";
let motivo = "";
let corpo = null;

try {
    corpo = JSON.parse(texto);
} catch (e) {
    estado = "recusada";
    motivo = "não é JSON";
}

if (corpo && topico.indexOf("application/") === 0) {
    if (topico.indexOf("/event/up") !== topico.length - 9) {
        estado = "ignorada";
        motivo = "evento do ChirpStack que não é uplink";
        corpo = null;
    } else if (corpo.object && typeof corpo.object === "object") {
        corpo = corpo.object;
    } else if (corpo.data) {
        try {
            corpo = JSON.parse(Buffer.from(corpo.data, "base64").toString("utf8"));
        } catch (e) {
            estado = "recusada";
            motivo = "payload binário — falta codec no ChirpStack";
            corpo = null;
        }
    }
} else if (corpo && topico.indexOf("zigbee2mqtt/bridge") === 0) {
    estado = "ignorada";
    motivo = "tópico interno do Z2M";
    corpo = null;
}

if (corpo && estado === "aceita") {
    const achadas = MEDIDAS.filter(k => typeof corpo[k] === "number");
    if (!achadas.length) {
        estado = "recusada";
        motivo = "sem grandezas reconhecidas: " + Object.keys(corpo).join(", ");
    } else {
        motivo = achadas.map(k => k + "=" + corpo[k]).join("  ");
    }
}

const registro = {
    hora: new Date().toLocaleTimeString("pt-BR"),
    topico: topico,
    estado: estado,
    motivo: motivo,
    // Corta o payload: um uplink do ChirpStack tem centenas de caracteres e
    // empurraria o resto da linha para fora da tela.
    bruto: texto.length > 110 ? texto.slice(0, 110) + "…" : texto
};

const log = flow.get("trafego") || [];
log.unshift(registro);
if (log.length > 30) { log.length = 30; }   // teto: a box tem 1,8 GB
flow.set("trafego", log);

msg.payload = log;
return msg;
""".strip(), 400, 1285, [[nid("tpl-trafego")]])

modelo("tpl-trafego", "grp-traf", "log do MQTT", 1, """
<style>
.traf { font-family:ui-monospace,Consolas,monospace; font-size:11px; }
.traf div.l { padding:3px 0; border-bottom:1px solid rgba(128,128,128,.2); }
.traf .hora { opacity:.55; }
.traf .top { color:#90caf9; }
.traf .aceita   { color:#8bc34a; font-weight:600; }
.traf .recusada { color:#e53935; font-weight:600; }
.traf .ignorada { color:#9e9e9e; font-weight:600; }
.traf .mot { opacity:.85; }
.traf .cru { opacity:.45; display:block; margin-left:8px;
             word-break:break-all; }
</style>
<div class="traf">
  <div class="l" ng-repeat="m in msg.payload track by $index">
    <span class="hora">{{m.hora}}</span>
    <span class="{{m.estado}}">[{{m.estado}}]</span>
    <span class="top">{{m.topico}}</span>
    <span class="mot">— {{m.motivo}}</span>
    <span class="cru">{{m.bruto}}</span>
  </div>
  <div ng-if="!msg.payload || msg.payload.length === 0"
       style="opacity:.6; font-style:italic; padding:10px">
    Nada no MQTT ainda. Clique num botão de teste, ou espere um sensor reportar.
  </div>
</div>
""", 12, 700, 1285)

# ------------------------------------------------------- erros do SQLite
add(id=nid("catch-sql"), type="catch", z=FLOW, name="erros do banco",
    scope=None, uncaught=False, x=150, y=1420, wires=[[nid("fn-erro")]])

fn("fn-erro", "explicar erro", r"""
/* Erro mais comum aqui: "SQLITE_CANTOPEN" ou "no such table". Nos dois casos
 * a causa costuma ser permissão — em WAL o LEITOR também precisa escrever
 * (cria os arquivos -wal e -shm), então ler o banco exige permissão de
 * escrita no diretório /var/lib/hub, e não só no arquivo. */
const erro = (msg.error && msg.error.message) || "erro desconhecido";
let dica = "";

if (/CANTOPEN|unable to open/i.test(erro)) {
    dica = "O usuário do Node-RED não consegue abrir o banco. Em WAL, ler "
         + "exige escrever: dê permissão no DIRETÓRIO /var/lib/hub, não só "
         + "no arquivo .db.";
} else if (/no such table|no such column/i.test(erro)) {
    dica = "Esquema desatualizado ou caminho errado. Rode o schema.sql e a "
         + "migração; confira o caminho no nó de configuração do SQLite.";
} else if (/readonly/i.test(erro)) {
    dica = "Banco aberto somente-leitura. Os botões de limpeza precisam de "
         + "escrita.";
}

msg.payload = [{ estado: "mau", texto: erro, detalhe: dica }];
msg.quando = new Date().toLocaleString("pt-BR");
return msg;
""".strip(), 360, 1420, [[nid("tpl-diag")]])

destino = pathlib.Path(__file__).with_name("dashboard-hub.json")
destino.parent.mkdir(parents=True, exist_ok=True)
destino.write_text(json.dumps(N, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
print(f"{len(N)} nós -> {destino}")
