import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';

// Recuperação de senha em dois passos: pedir o código e cadastrar a nova senha.
//
// É esta tela que impede a conta de se perder — e, com ela, o dispositivo de
// ficar preso a um dono que não consegue mais entrar. Redefinir a senha também
// encerra todas as sessões e para as notificações nos aparelhos antigos: se a
// conta tinha sido tomada, quem estava dentro sai agora.
class ForgotPasswordPage extends StatefulWidget {
  const ForgotPasswordPage({super.key});

  @override
  State<ForgotPasswordPage> createState() => _ForgotPasswordPageState();
}

class _ForgotPasswordPageState extends State<ForgotPasswordPage> {
  static const int minSenha = 8;

  final _email = TextEditingController();
  final _code = TextEditingController();
  final _pass = TextEditingController();
  bool _pediu = false;
  bool _busy = false;
  bool _verSenha = false;
  String? _error;
  int _espera = 0;
  Timer? _tick;

  static const Map<String, String> _mensagens = {
    'invalid_code': 'Código incorreto. Confira os 6 dígitos.',
    'expired': 'O código expirou. Peça um novo.',
    'no_code': 'Nenhum código pendente. Peça um novo.',
    'too_many_attempts':
        'Tentativas demais. Peça um novo código e tente de novo.',
    'weak_password': 'A senha precisa de pelo menos $minSenha caracteres.',
    'network': 'Não foi possível conectar ao servidor.\n'
        'Verifique a conexão (o Tailscale está ligado?).',
    'http_404': 'O servidor não tem a rota de recuperação.\n'
        'Falta importar o flow "api-email" no Node-RED.',
  };

  @override
  void dispose() {
    _tick?.cancel();
    _email.dispose();
    _code.dispose();
    _pass.dispose();
    super.dispose();
  }

  void _contarRegressiva() {
    _tick?.cancel();
    setState(() => _espera = 60);
    _tick = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => _espera--);
      if (_espera <= 0) t.cancel();
    });
  }

  Future<void> _pedirCodigo() async {
    final email = _email.text.trim();
    if (!email.contains('@')) {
      setState(() => _error = 'Digite um e-mail válido.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    await ApiService.requestEmailCode(email, 'reset');
    if (!mounted) return;
    // A tela avança mesmo se a conta não existir. O servidor responde igual nos
    // dois casos de propósito, e a interface não pode desfazer isso dizendo
    // "este e-mail não tem cadastro" — seria uma consulta de quem tem conta.
    setState(() {
      _busy = false;
      _pediu = true;
    });
    _contarRegressiva();
  }

  Future<void> _redefinir() async {
    final codigo = _code.text.trim();
    if (codigo.length != 6) {
      setState(() => _error = 'Digite os 6 dígitos do código.');
      return;
    }
    if (_pass.text.length < minSenha) {
      setState(() => _error = _mensagens['weak_password']);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final erro = await ApiService.resetPassword(
        _email.text.trim(), codigo, _pass.text);
    if (!mounted) return;
    if (erro == null) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Senha alterada. Entre com a nova senha.')));
      return;
    }
    setState(() {
      _busy = false;
      _error = _mensagens[erro] ??
          (erro.startsWith('http_')
              ? 'O servidor recusou (HTTP ${erro.substring(5)}).'
              : 'Não foi possível redefinir a senha.');
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Recuperar senha')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Icon(Icons.lock_reset, size: 56, color: Colors.indigo),
          const SizedBox(height: 16),
          Text(
            _pediu
                ? 'Se houver uma conta com esse e-mail, o código chegou lá. '
                    'Ele vale por 15 minutos.'
                : 'Enviaremos um código de 6 dígitos para o e-mail da conta.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _email,
            enabled: !_pediu,
            keyboardType: TextInputType.emailAddress,
            autocorrect: false,
            decoration: const InputDecoration(
                labelText: 'E-mail', border: OutlineInputBorder()),
            onSubmitted: (_) => _pedirCodigo(),
          ),
          if (_pediu) ...[
            const SizedBox(height: 12),
            TextField(
              controller: _code,
              keyboardType: TextInputType.number,
              maxLength: 6,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 24, letterSpacing: 8),
              decoration: const InputDecoration(
                labelText: 'Código',
                border: OutlineInputBorder(),
                counterText: '',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pass,
              obscureText: !_verSenha,
              decoration: InputDecoration(
                labelText: 'Nova senha',
                border: const OutlineInputBorder(),
                helperText: 'Mínimo de $minSenha caracteres',
                suffixIcon: IconButton(
                  icon:
                      Icon(_verSenha ? Icons.visibility_off : Icons.visibility),
                  onPressed: () => setState(() => _verSenha = !_verSenha),
                ),
              ),
              onSubmitted: (_) => _redefinir(),
            ),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _busy ? null : (_pediu ? _redefinir : _pedirCodigo),
            child: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : Text(_pediu ? 'Alterar senha' : 'Enviar código'),
          ),
          if (_pediu)
            TextButton(
              onPressed: (_busy || _espera > 0) ? null : _pedirCodigo,
              child: Text(_espera > 0
                  ? 'Reenviar código (${_espera}s)'
                  : 'Reenviar código'),
            ),
        ],
      ),
    );
  }
}
