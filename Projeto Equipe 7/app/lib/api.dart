import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'config.dart';

// Cliente da API HTTP do servidor (Node-RED). Chamadas com timeout curto.
class ApiService {
  static const Duration _timeout = Duration(seconds: 8);

  // Lança exceção em falha de rede; retorna null em credenciais inválidas (401).
  static Future<String?> login(String email, String password) async {
    final r = await http
        .post(Uri.parse('$apiBase/login'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'email': email, 'password': password}))
        .timeout(_timeout);
    if (r.statusCode == 200) {
      return (jsonDecode(r.body) as Map<String, dynamic>)['token'] as String?;
    }
    return null;
  }

  // Cria a conta e já devolve a sessão. Em caso de recusa, devolve o motivo
  // ('email_taken', 'weak_password', 'invalid_email' ou 'network').
  static Future<({String? token, String? error})> register(
      String email, String password, String name) async {
    http.Response r;
    try {
      r = await http
          .post(Uri.parse('$apiBase/register'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(
                  {'email': email, 'password': password, 'name': name}))
          .timeout(_timeout);
    } catch (_) {
      return (token: null, error: 'network'); // só aqui é falha de conexão
    }
    // Uma rota ausente responde em HTML: tratar isso como "sem conexão"
    // mandaria procurar o problema no lugar errado.
    Map<String, dynamic>? b;
    try {
      b = jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {}
    final t = b?['token']?.toString();
    if (r.statusCode == 200 && t != null) return (token: t, error: null);
    final e = b?['error']?.toString();
    return (token: null, error: e ?? 'http_${r.statusCode}');
  }

  // Lança exceção em falha (rede ou status != 200).
  static Future<List<dynamic>> devices(String token) async {
    final r = await http
        .get(Uri.parse('$apiBase/devices'),
            headers: {'Authorization': 'Bearer $token'})
        .timeout(_timeout);
    if (r.statusCode == 200) return jsonDecode(r.body) as List<dynamic>;
    throw Exception('status ${r.statusCode}');
  }

  static Future<Map<String, dynamic>?> claimToken(String token) async {
    try {
      final r = await http
          .post(Uri.parse('$apiBase/claim-token'),
              headers: {'Authorization': 'Bearer $token'})
          .timeout(_timeout);
      if (r.statusCode == 200) {
        return jsonDecode(r.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
  }

  static Future<List<dynamic>> events(String token, String deviceId) async {
    try {
      final r = await http
          .get(Uri.parse('$apiBase/events?device=$deviceId'),
              headers: {'Authorization': 'Bearer $token'})
          .timeout(_timeout);
      if (r.statusCode == 200) return jsonDecode(r.body) as List<dynamic>;
    } catch (_) {}
    return [];
  }

  static Future<void> registerPush(String token, String fcmToken) async {
    try {
      await http.post(
        Uri.parse('$apiBase/register-push'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'fcm_token': fcmToken}),
      ).timeout(_timeout);
    } catch (_) {}
  }

  // Preferencias de notificacao DESTE celular. Nao vao para a TV box: la o
  // arquivo e unico para todos os aparelhos, e silenciar o aviso num telefone
  // silenciava em todos. A identidade do celular e o proprio token FCM.
  static Future<Map<String, dynamic>?> pushNotify(
      String token, String fcmToken) async {
    try {
      final r = await http.get(
        Uri.parse('$apiBase/push-notify')
            .replace(queryParameters: {'fcm_token': fcmToken}),
        headers: {'Authorization': 'Bearer $token'},
      ).timeout(_timeout);
      if (r.statusCode != 200) return null;
      final d = jsonDecode(r.body);
      return d is Map<String, dynamic> ? d : null;
    } catch (_) {
      return null;
    }
  }

  static Future<bool> setPushNotify(
      String token, String fcmToken, Map<String, bool> notify) async {
    try {
      final r = await http.post(
        Uri.parse('$apiBase/push-notify'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'fcm_token': fcmToken, 'notify': notify}),
      ).timeout(_timeout);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // Ao sair da conta: sem isto o aparelho continuaria recebendo os alertas.
  static Future<void> unregisterPush(String token, String fcmToken) async {
    try {
      await http.post(
        Uri.parse('$apiBase/unregister-push'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'fcm_token': fcmToken}),
      ).timeout(_timeout);
    } catch (_) {}
  }

  // Baixa um trecho gravado como MP4, em fluxo, informando o progresso.
  //
  // O token vai no CABEÇALHO, e não na query como o player faz: aqui o arquivo
  // acaba compartilhado com outra pessoa ou aplicativo, e uma URL com token
  // dentro sobreviveria em histórico e lista de recentes.
  //
  // Sem timeout curto de propósito: a box remuxa o trecho antes de mandar o
  // primeiro byte, e meia hora de vídeo leva um tempo nisso.
  static Future<bool> baixarClipe({
    required String path,
    required DateTime inicio,
    required int segundos,
    required String destino,
    String? token,
    void Function(int recebidos, int? total)? progresso,
  }) async {
    final uri = Uri.parse('$clipBase/clip').replace(queryParameters: {
      'path': path,
      'start': inicio.toUtc().toIso8601String(),
      'duration': segundos.toString(),
    });
    final cliente = http.Client();
    IOSink? saida;
    try {
      final req = http.Request('GET', uri)..headers.addAll(_midia(token));
      final resp = await cliente.send(req);
      if (resp.statusCode != 200) return false;
      final arq = File(destino);
      saida = arq.openWrite();
      var recebidos = 0;
      await for (final pedaco in resp.stream) {
        saida.add(pedaco);
        recebidos += pedaco.length;
        progresso?.call(recebidos, resp.contentLength);
      }
      await saida.flush();
      await saida.close();
      saida = null;
      // Arquivo vazio é falha silenciosa do remux; não vale entregar.
      return await arq.length() > 0;
    } catch (_) {
      try {
        await saida?.close();
      } catch (_) {}
      return false;
    } finally {
      cliente.close();
    }
  }

  // Cabeçalho de acesso aos serviços da box. O token vem de deviceToken().
  static Map<String, String> _midia(String? token) =>
      token == null ? {} : {'Authorization': 'Bearer $token'};

  // Token de mídia do aparelho, entregue pelo servidor só ao dono. É ele que
  // abre a 9997 e o MediaMTX; embutir no app seria publicá-lo.
  static Future<String?> deviceToken(String session, String deviceId) async {
    try {
      final r = await http.get(
          Uri.parse('$apiBase/device-token?device=$deviceId'),
          headers: {'Authorization': 'Bearer $session'}).timeout(_timeout);
      if (r.statusCode == 200) {
        return (jsonDecode(r.body) as Map<String, dynamic>)['token'] as String?;
      }
    } catch (_) {}
    return null;
  }

  // Lista dinâmica de câmeras da TV box (detectadas automaticamente).
  static Future<Map<String, dynamic>?> cameras([String? token]) async {
    try {
      final r = await http
          .get(Uri.parse('$clipBase/cameras'), headers: _midia(token))
          .timeout(_timeout);
      if (r.statusCode == 200) return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {}
    return null;
  }

  // Espaço em disco da TV box e autonomia estimada de gravação.
  static Future<Map<String, dynamic>?> storage([String? token]) async {
    try {
      final r = await http
          .get(Uri.parse('$clipBase/storage'), headers: _midia(token))
          .timeout(_timeout);
      if (r.statusCode == 200) return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {}
    return null;
  }

  // Grava qualidade/retenção por câmera. Demora mais: a TV box reinicia a
  // captura para aplicar a nova configuração.
  // Desfaz o pareamento da GuardianBox: o servidor solta o dono e manda a box
  // apagar o Wi-Fi e voltar a ler QR. Devolve 'ok', 'offline' ou 'erro'.
  static Future<String> esquecerBox(String session, String deviceId,
      {required bool apagarGravacoes}) async {
    try {
      final r = await http
          .post(Uri.parse('$apiBase/forget-device'),
              headers: {
                'Authorization': 'Bearer $session',
                'Content-Type': 'application/json',
              },
              body: jsonEncode({
                'device': deviceId,
                'apagar_gravacoes': apagarGravacoes,
              }))
          .timeout(const Duration(seconds: 20));
      if (r.statusCode == 200) return 'ok';
      if (r.statusCode == 409) return 'offline';
      return 'erro';
    } catch (_) {
      return 'erro';
    }
  }

  // Esquece uma câmera na box: configuração, vaga e gravações. Timeout longo
  // porque a box para o MediaMTX, apaga a pasta e redetecta as câmeras antes
  // de responder. Devolve os bytes apagados, ou null se falhou.
  static Future<int?> esquecerCamera(String id, [String? token]) async {
    try {
      final r = await http
          .post(Uri.parse('$clipBase/forget'),
              headers: {'Content-Type': 'application/json', ..._midia(token)},
              body: jsonEncode({'id': id}))
          .timeout(const Duration(seconds: 120));
      if (r.statusCode != 200) return null;
      final d = jsonDecode(r.body);
      return (d is Map ? d['apagado_bytes'] as num? : null)?.toInt() ?? 0;
    } catch (_) {
      return null;
    }
  }

  static Future<bool> saveSettings(Map<String, dynamic> body,
      [String? token]) async {
    try {
      final r = await http
          .post(Uri.parse('$clipBase/settings'),
              headers: {'Content-Type': 'application/json', ..._midia(token)},
              body: jsonEncode(body))
          .timeout(const Duration(seconds: 40));
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // A listagem passou a vir do clip-server: a porta 9996 do MediaMTX não tem
  // autenticação e, por isso, não é publicada — quem sai da box é só a 9997.
  static Future<List<dynamic>> recordings(String path, [String? token]) async {
    try {
      final r = await http
          .get(Uri.parse('$clipBase/list?path=$path'), headers: _midia(token))
          .timeout(_timeout);
      if (r.statusCode == 200) return jsonDecode(r.body) as List<dynamic>;
    } catch (_) {}
    return [];
  }

  // Pede o código de 6 dígitos por e-mail. purpose: 'verify' ou 'reset'.
  //
  // Responde sempre sucesso, mesmo quando o e-mail não tem conta: se a resposta
  // distinguisse os casos, qualquer pessoa poderia usar esta rota para
  // descobrir quem tem cadastro.
  static Future<bool> requestEmailCode(String email, String purpose) async {
    try {
      final r = await http
          .post(Uri.parse('$apiBase/email/request-code'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'email': email, 'purpose': purpose}))
          .timeout(_timeout);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // Confirma o e-mail. Devolve null em sucesso, ou o motivo da recusa.
  static Future<String?> confirmEmail(String email, String code) async {
    return _codigo('$apiBase/email/confirm', {'email': email, 'code': code});
  }

  // Redefine a senha provando controle da caixa de e-mail.
  static Future<String?> resetPassword(
      String email, String code, String password) async {
    return _codigo('$apiBase/password-reset',
        {'email': email, 'code': code, 'password': password});
  }

  static Future<String?> _codigo(String url, Map<String, String> body) async {
    http.Response r;
    try {
      r = await http
          .post(Uri.parse(url),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(body))
          .timeout(_timeout);
    } catch (_) {
      return 'network';
    }
    if (r.statusCode == 200) return null;
    Map<String, dynamic>? b;
    try {
      b = jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {}
    return b?['error']?.toString() ?? 'http_${r.statusCode}';
  }

  // Dono da sessão atual. Necessário porque o app guarda o token e nas
  // aberturas seguintes não passa pelo login — sem isto, quem já estava logado
  // com e-mail não confirmado nunca ficaria sabendo.
  //
  // Devolve null quando a sessão morreu (401) ou o servidor não respondeu; o
  // chamador trata os dois casos igual, escondendo o aviso em vez de alarmar
  // por um problema de rede.
  static Future<Map<String, dynamic>?> me(String token) async {
    try {
      final r = await http.get(Uri.parse('$apiBase/me'),
          headers: {'Authorization': 'Bearer $token'}).timeout(_timeout);
      if (r.statusCode == 200) {
        return jsonDecode(r.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
  }

  // Envia um comando ao aparelho pelo servidor, que repassa ao broker.
  //
  // O app não fala MQTT: assim o broker não precisa ser publicado na internet,
  // e a credencial dele não viaja dentro do APK — qualquer pessoa que extraia
  // um APK leria uma senha embutida ali.
  static Future<bool> command(String session, String deviceId, String module,
      String action, [Map<String, dynamic>? args]) async {
    try {
      final r = await http
          .post(Uri.parse('$apiBase/command'),
              headers: {
                'Authorization': 'Bearer $session',
                'Content-Type': 'application/json',
              },
              body: jsonEncode({
                'device': deviceId,
                'module': module,
                'action': action,
                'args': ?args,
              }))
          .timeout(_timeout);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // Estado do disparo por movimento, lido da própria box.
  // A box é a fonte da verdade: é ela que decide se toca, e é nela que o
  // estado sobrevive a reboot e a queda de rede.
  static Future<Map<String, dynamic>?> alarmState([String? token]) async {
    try {
      final r = await http
          .get(Uri.parse('$clipBase/alarm'), headers: _midia(token))
          .timeout(_timeout);
      if (r.statusCode == 200) {
        return jsonDecode(r.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
  }

  static Future<bool> setAlarm(bool armed, int seconds, [String? token]) async {
    try {
      final r = await http
          .post(Uri.parse('$clipBase/alarm'),
              headers: {'Content-Type': 'application/json', ..._midia(token)},
              body: jsonEncode({'armed': armed, 'seconds': seconds}))
          .timeout(_timeout);
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
