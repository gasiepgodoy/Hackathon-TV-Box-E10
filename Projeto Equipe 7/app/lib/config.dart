// ===== Configuração do piloto =====
// Preencha com os endereços/credenciais do SEU ambiente.
// (Credenciais reais NÃO devem ser versionadas — estes são placeholders.)

const String apiBase = 'https://api.SEU_DOMINIO/api'; // Node-RED, pelo túnel

// MQTT (tempo real: status, eventos, comandos)
const String brokerHost = 'SEU_SERVIDOR';
const int brokerPort = 1883;
const String brokerUser = 'serverapp';
const String brokerPass = 'SUA_SENHA_MQTT';

// Serviços de mídia na TV box. Os dois exigem o token do aparelho, que o app
// busca em /api/device-token — nunca vem embutido aqui, porque APK se desmonta.
const String whepBase = 'https://cam.SEU_DOMINIO';   // MediaMTX (ao vivo)
const String clipBase = 'https://clip.SEU_DOMINIO';  // clip-server (clipes e lista)

// Usuário fixo do MediaMTX; a senha é o token do aparelho.
const String mediaUser = 'app';

// Câmeras da TV box (paths do MediaMTX)
class CamInfo {
  final String name;
  final String path;
  const CamInfo(this.name, this.path);
}

const List<CamInfo> cameras = [
  CamInfo('Câmera 1', 'cam'),
  CamInfo('Câmera 2', 'cam2'),
];
