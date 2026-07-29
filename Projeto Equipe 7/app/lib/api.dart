import 'dart:convert';
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

  // Lista dinâmica de câmeras da TV box (detectadas automaticamente).
  static Future<Map<String, dynamic>?> cameras() async {
    try {
      final r =
          await http.get(Uri.parse('$clipBase/cameras')).timeout(_timeout);
      if (r.statusCode == 200) return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {}
    return null;
  }

  static Future<List<dynamic>> recordings(String path) async {
    try {
      final r = await http
          .get(Uri.parse('$recBase/list?path=$path'))
          .timeout(_timeout);
      if (r.statusCode == 200) return jsonDecode(r.body) as List<dynamic>;
    } catch (_) {}
    return [];
  }
}
