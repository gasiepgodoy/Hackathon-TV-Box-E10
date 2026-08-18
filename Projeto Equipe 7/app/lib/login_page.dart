import 'package:flutter/material.dart';
import 'api.dart';
import 'session.dart';
import 'register_page.dart';
import 'forgot_password_page.dart';

class LoginPage extends StatefulWidget {
  final void Function(String token) onLoggedIn;
  const LoginPage({super.key, required this.onLoggedIn});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _email = TextEditingController();
  final _pass = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _login() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final token = await ApiService.login(_email.text.trim(), _pass.text);
      if (token != null) {
        await Session.save(token);
        widget.onLoggedIn(token);
      } else {
        setState(() {
          _busy = false;
          _error = 'E-mail ou senha inválidos';
        });
      }
    } catch (_) {
      setState(() {
        _busy = false;
        _error =
            'Não foi possível conectar ao servidor.\nVerifique a conexão (o Tailscale está ligado?).';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Entrar')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.shield, size: 64, color: Colors.indigo),
            const SizedBox(height: 24),
            TextField(
              controller: _email,
              decoration: const InputDecoration(
                  labelText: 'E-mail', border: OutlineInputBorder()),
              keyboardType: TextInputType.emailAddress,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pass,
              decoration: const InputDecoration(
                  labelText: 'Senha', border: OutlineInputBorder()),
              obscureText: true,
              onSubmitted: (_) => _login(),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: const TextStyle(color: Colors.red)),
              ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _busy ? null : _login,
                child: _busy
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Entrar'),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) => const ForgotPasswordPage()),
                      ),
              child: const Text('Esqueci minha senha'),
            ),
            TextButton(
              onPressed: _busy
                  ? null
                  : () => Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) =>
                                RegisterPage(onLoggedIn: widget.onLoggedIn)),
                      ),
              child: const Text('Criar uma conta'),
            ),
          ],
        ),
      ),
    );
  }
}
