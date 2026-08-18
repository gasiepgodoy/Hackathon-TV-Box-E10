import 'package:flutter/material.dart';
import 'api.dart';
import 'session.dart';
import 'verify_email_page.dart';

// Criação de conta. Valida no aparelho o que dá para validar sem ida ao
// servidor, para o usuário não descobrir um erro banal depois da espera.
class RegisterPage extends StatefulWidget {
  final void Function(String token) onLoggedIn;
  const RegisterPage({super.key, required this.onLoggedIn});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  static const int minSenha = 8;

  final _name = TextEditingController();
  final _email = TextEditingController();
  final _pass = TextEditingController();
  final _pass2 = TextEditingController();
  bool _busy = false;
  bool _verSenha = false;
  String? _error;

  static const Map<String, String> _mensagens = {
    'email_taken': 'Este e-mail já tem uma conta. Tente entrar.',
    'invalid_email': 'E-mail inválido.',
    'weak_password': 'A senha precisa de pelo menos $minSenha caracteres.',
    'network': 'Não foi possível conectar ao servidor.\n'
        'Verifique a conexão (o Tailscale está ligado?).',
    'http_404': 'O servidor não tem a rota de cadastro.\n'
        'Falta importar o flow "api-cadastro" no Node-RED.',
  };

  String _mensagem(String? code) {
    final m = _mensagens[code];
    if (m != null) return m;
    if (code != null && code.startsWith('http_')) {
      return 'O servidor recusou o cadastro (HTTP ${code.substring(5)}).';
    }
    return 'Não foi possível criar a conta.';
  }

  bool get _emailOk =>
      RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(_email.text.trim());

  Future<void> _criar() async {
    final senha = _pass.text;
    String? erroLocal;
    if (!_emailOk) {
      erroLocal = 'Informe um e-mail válido.';
    } else if (senha.length < minSenha) {
      erroLocal = 'A senha precisa de pelo menos $minSenha caracteres.';
    } else if (senha != _pass2.text) {
      erroLocal = 'As senhas não conferem.';
    }
    if (erroLocal != null) {
      setState(() => _error = erroLocal);
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    final r = await ApiService.register(
        _email.text.trim(), senha, _name.text.trim());
    if (!mounted) return;
    if (r.token != null) {
      await Session.save(r.token!);
      if (!mounted) return;
      // A confirmação vem logo após criar a conta, que é quando o e-mail está
      // fresco na cabeça e o usuário ainda está disposto. Deixar para depois
      // significa nunca, e conta sem e-mail confirmado é conta perdível.
      await Navigator.push<bool>(
        context,
        MaterialPageRoute(
            builder: (_) => VerifyEmailPage(email: _email.text.trim())),
      );
      if (!mounted) return;
      Navigator.pop(context);
      widget.onLoggedIn(r.token!);
      return;
    }
    setState(() {
      _busy = false;
      _error = _mensagem(r.error);
    });
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _pass.dispose();
    _pass2.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Criar conta')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          TextField(
            controller: _name,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(
                labelText: 'Nome', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            decoration: const InputDecoration(
                labelText: 'E-mail', border: OutlineInputBorder()),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pass,
            obscureText: !_verSenha,
            decoration: InputDecoration(
              labelText: 'Senha',
              border: const OutlineInputBorder(),
              helperText: 'Mínimo de $minSenha caracteres',
              suffixIcon: IconButton(
                icon: Icon(_verSenha ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _verSenha = !_verSenha),
              ),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _pass2,
            obscureText: !_verSenha,
            decoration: const InputDecoration(
                labelText: 'Repita a senha', border: OutlineInputBorder()),
            onSubmitted: (_) => _criar(),
            onChanged: (_) => setState(() {}),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _busy ? null : _criar,
            child: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Criar conta'),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _busy ? null : () => Navigator.pop(context),
            child: const Text('Já tenho conta'),
          ),
        ],
      ),
    );
  }
}
