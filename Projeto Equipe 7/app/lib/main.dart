import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'session.dart';
import 'login_page.dart';
import 'devices_page.dart';
import 'push_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await PushService.initApp();
  runApp(const GuardianHubApp());
}

class GuardianHubApp extends StatelessWidget {
  const GuardianHubApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Guardian Hub',
      debugShowCheckedModeBanner: false,
      // Identidade Guardian Co.: navy do logo como cor-semente e barra
      // superior navy com texto branco em todas as telas.
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF0B1A3C),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0B1A3C),
          foregroundColor: Colors.white,
        ),
      ),
      // O app é todo em português, mas os seletores de data e hora são widgets
      // do sistema: sem declarar o idioma eles saem em inglês, e o de hora vem
      // em AM/PM. Como pt_BR é o único suportado, qualquer idioma do aparelho
      // resolve para ele.
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('pt', 'BR')],
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
