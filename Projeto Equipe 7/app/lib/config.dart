// ===== Configuração do piloto =====
// Preencha com os endereços/credenciais do SEU ambiente.
// (Credenciais reais NÃO devem ser versionadas — estes são placeholders.)

const String apiBase = 'http://SEU_SERVIDOR:1880/api'; // Node-RED no servidor

// MQTT (tempo real: status, eventos, comandos)
const String brokerHost = 'SEU_SERVIDOR';
const int brokerPort = 1883;
const String brokerUser = 'serverapp';
const String brokerPass = 'SUA_SENHA_MQTT';

// Vídeo ao vivo (piloto: 1 câmera; no futuro viria do servidor por dispositivo)
const String whepUrl = 'http://SUA_TVBOX:8889/cam/whep';

// Gravações (servidor de playback do MediaMTX na TV box)
const String recBase = 'http://SUA_TVBOX:9996';
const String recPath = 'cam';

// Serviço de remux (TV box): entrega a fatia como MP4 navegável (seek + duração)
const String clipBase = 'http://SUA_TVBOX:9997';
