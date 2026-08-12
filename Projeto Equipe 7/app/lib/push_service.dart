import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'api.dart';

// Handler de mensagens em background (mensagens do tipo "notification" já são
// exibidas pelo sistema; aqui só garantimos o registro do handler).
@pragma('vm:entry-point')
Future<void> firebaseBgHandler(RemoteMessage message) async {}

class PushService {
  // Chamado no start do app (antes do runApp).
  static Future<void> initApp() async {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(firebaseBgHandler);
  }

  // Chamado quando há sessão: pede permissão, pega o token FCM e registra no servidor.
  static Future<void> register(String sessionToken) async {
    final fm = FirebaseMessaging.instance;
    await fm.requestPermission();
    final fcmToken = await fm.getToken();
    if (fcmToken != null) {
      await ApiService.registerPush(sessionToken, fcmToken);
    }
    fm.onTokenRefresh
        .listen((t) => ApiService.registerPush(sessionToken, t));
  }

  // Chamado ao sair da conta, antes de descartar a sessão: o servidor precisa
  // do token de sessão para saber de quem é o aparelho.
  static Future<void> unregister(String sessionToken) async {
    try {
      final fcmToken = await FirebaseMessaging.instance.getToken();
      if (fcmToken != null) {
        await ApiService.unregisterPush(sessionToken, fcmToken);
      }
    } catch (_) {}
  }
}
