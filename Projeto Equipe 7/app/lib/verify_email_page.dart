import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';

// Confirmação do e-mail por código de 6 dígitos.
//
// Código digitado, e não link clicado: o servidor só é alcançável pela
// Tailscale, então um link no e-mail abriria no navegador do celular e não
// chegaria a lugar nenhum. O app já fala com a API, e usa o caminho que existe.
//
// A tela não bloqueia o uso do app — quem pular continua entrando normalmente.
// Ela existe para que a conta seja recuperável depois: sem e-mail confirmado,
// senha esquecida significa dispositivo preso a um dono que não volta mais.
class VerifyEmailPage extends StatefulWidget {
  final String email;
  final bool podePular;
  const VerifyEmailPage({
    super.key,
    required this.email,
    this.podePular = true,
  });

  @override
  State<VerifyEmailPage> createState() => _VerifyEmailPageState();
}

class _VerifyEmailPageState extends State<VerifyEmailPage> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _aviso;
  int _espera = 0; // segundos até poder reenviar
  Timer? _tick;

  static const Map<String, String> _mensagens = {
    'invalid_code': 'Código incorreto. Confira os 6 dígitos.',
    'expired': 'O código expirou. Peça um novo.',
    'no_code': 'Nenhum código pendente. Peça um novo.',
    'too_many_attempts':
        'Tentativas demais. Peça um novo código e tente de novo.',
    'network': 'Não foi possível conectar ao servidor.\n'
        'Verifique a conexão (o Tailscale está ligado?).',
    'http_404': 'O servidor não tem a rota de confirmação.\n'
        'Falta importar o flow "api-email" no Node-RED.',
  };

  @override
  void initState() {
    super.initState();
    _pedirCodigo(inicial: true);
  }

  @override
  void dispose() {
    _tick?.cancel();
    _code.dispose();
    super.dispose();
  }

  // O servidor recusa um novo código por minuto. A contagem aqui é só para o
  // usuário não ficar apertando "reenviar" e achar que nada acontece — a
  // resposta do servidor é sempre a mesma, de propósito.
  void _contarRegressiva() {
    _tick?.cancel();
    setState(() => _espera = 60);
    _tick = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => _espera--);
      if (_espera <= 0) t.cancel();
    });
  }

  Future<void> _pedirCodigo({bool inicial = false}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final ok = await ApiService.requestEmailCode(widget.email, 'verify');
    if (!mounted) return;
    setState(() {
      _busy = false;
      _aviso = ok
          ? 'Enviamos um código para ${widget.email}.'
          : 'Não conseguimos falar com o servidor agora.';
    });
    if (ok) _contarRegressiva();
  }

  Future<void> _confirmar() async {
    final codigo = _code.text.trim();
    if (codigo.length != 6) {
      setState(() => _error = 'Digite os 6 dígitos do código.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final erro = await ApiService.confirmEmail(widget.email, codigo);
    if (!mounted) return;
    if (erro == null) {
      Navigator.pop(context, true);
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('E-mail confirmado.')));
      return;
    }
    setState(() {
      _busy = false;
      _error = _mensagens[erro] ??
          (erro.startsWith('http_')
              ? 'O servidor recusou (HTTP ${erro.substring(5)}).'
              : 'Não foi possível confirmar.');
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Confirmar e-mail'),
        automaticallyImplyLeading: widget.podePular,
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Icon(Icons.mark_email_read, size: 56, color: Colors.indigo),
          const SizedBox(height: 16),
          Text(
            'Confirmar o e-mail é o que permite recuperar a conta se você '
            'esquecer a senha. Sem isso, não há como voltar — e os '
            'dispositivos ficam presos à conta antiga.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (_aviso != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_aviso!,
                  style: const TextStyle(fontWeight: FontWeight.w500)),
            ),
          const SizedBox(height: 20),
          TextField(
            controller: _code,
            keyboardType: TextInputType.number,
            maxLength: 6,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 28, letterSpacing: 10),
            decoration: const InputDecoration(
              labelText: 'Código',
              border: OutlineInputBorder(),
              counterText: '',
            ),
            onSubmitted: (_) => _confirmar(),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _confirmar,
            child: _busy
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Confirmar'),
          ),
          TextButton(
            onPressed: (_busy || _espera > 0) ? null : _pedirCodigo,
            child: Text(_espera > 0
                ? 'Reenviar código (${_espera}s)'
                : 'Reenviar código'),
          ),
          if (widget.podePular)
            TextButton(
              onPressed: _busy ? null : () => Navigator.pop(context, false),
              child: const Text('Confirmar depois'),
            ),
        ],
      ),
    );
  }
}
