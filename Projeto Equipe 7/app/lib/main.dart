import 'package:flutter/material.dart';
import 'session.dart';
import 'login_page.dart';
import 'devices_page.dart';
import 'push_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await PushService.initApp();
  runApp(const SecBoxApp());
}

class SecBoxApp extends StatelessWidget {
  const SecBoxApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SecBox',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: const RootPage(),
    );
  }
}

// Decide a tela inicial: login (sem token) ou lista de dispositivos (com token).
class RootPage extends StatefulWidget {
  const RootPage({super.key});
  @override
  State<RootPage> createState() => _RootPageState();
}

class _RootPageState extends State<RootPage> {
  String? _token;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final t = await Session.get();
    setState(() {
      _token = t;
      _loading = false;
    });
    if (t != null) PushService.register(t);
  }

  void _onLoggedIn(String t) {
    setState(() => _token = t);
    PushService.register(t);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_token == null) {
      return LoginPage(onLoggedIn: _onLoggedIn);
    }
    return DevicesPage(
      token: _token!,
      onLogout: () async {
        // desliga as notificações deste aparelho antes de perder a sessão
        await PushService.unregister(_token!);
        await Session.clear();
        setState(() => _token = null);
      },
    );
  }
}
