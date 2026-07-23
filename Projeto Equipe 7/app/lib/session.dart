import 'package:shared_preferences/shared_preferences.dart';

// Guarda o token de sessão entre aberturas do app.
class Session {
  static const _key = 'token';

  static Future<void> save(String token) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_key, token);
  }

  static Future<String?> get() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_key);
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_key);
  }
}
