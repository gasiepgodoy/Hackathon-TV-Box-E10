// Codec do nó BME280 — cole em ChirpStack → Device Profiles → <perfil> →
// aba "Codec" → Payload codec = "JavaScript functions".
//
// O nó envia JSON puro com chaves curtas para economizar bytes no ar
// (veja o comentário em montarPayload no .ino). Este codec devolve os nomes
// por extenso, que é o que aparece na coluna "Object" da aba Events.
//
// O hub NÃO depende deste codec: se "object" não vier, ele mesmo decodifica o
// base64 (_do_chirpstack em src/hub/coletor.py). O codec é para a interface —
// e para o dia em que outro consumidor ler o MQTT do ChirpStack.

function decodeUplink(input) {
  var texto = "";
  for (var i = 0; i < input.bytes.length; i++) {
    texto += String.fromCharCode(input.bytes[i]);
  }

  var bruto;
  try {
    bruto = JSON.parse(texto);
  } catch (e) {
    // Payload não-JSON: devolve o texto para dar o que depurar em vez de
    // um erro opaco na interface.
    return { errors: ["payload nao e JSON: " + texto] };
  }

  var saida = {};
  if (bruto.t !== undefined) saida.temperature = bruto.t;  // °C
  if (bruto.h !== undefined) saida.humidity = bruto.h;     // % UR
  if (bruto.p !== undefined) saida.pressure = bruto.p;     // hPa
  if (bruto.err !== undefined) saida.erro = bruto.err;     // sensor ausente

  return { data: saida };
}

// Downlink: 0x01 acende o LED do nó, qualquer outro valor apaga.
// (o tratamento está no case EV_TXCOMPLETE do firmware)
function encodeDownlink(input) {
  return { bytes: [input.data.led ? 1 : 0] };
}
