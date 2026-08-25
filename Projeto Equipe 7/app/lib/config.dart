// ===== Configuração do piloto =====
// Preencha com os endereços/credenciais do SEU ambiente.
// (Credenciais reais NÃO devem ser versionadas — estes são placeholders.)

const String apiBase = 'https://api.SEU_DOMINIO/api'; // Node-RED, pelo túnel

// O app NÃO fala MQTT. Comandos vão por POST /api/command e a presença vem de
// /api/devices — assim o broker não precisa ser publicado, e a credencial dele
// não é compilada dentro do APK, de onde qualquer pessoa poderia extraí-la.

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
