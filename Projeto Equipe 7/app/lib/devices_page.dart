import 'package:flutter/material.dart';
import 'api.dart';
import 'device_detail_page.dart';
import 'claim_page.dart';
import 'verify_email_page.dart';

class DevicesPage extends StatefulWidget {
  final String token;
  final Future<void> Function() onLogout;
  const DevicesPage({super.key, required this.token, required this.onLogout});
  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  List<dynamic> _devices = [];
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _conta;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final d = await ApiService.devices(widget.token);
      // Em paralelo, e sem deixar a lista depender disso: se /api/me falhar
      // (rota nao importada, rede instavel), a tela continua util.
      final c = await ApiService.me(widget.token);
      if (mounted) {
        setState(() {
          _devices = d;
          _conta = c;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _error =
              'Não foi possível conectar ao servidor.\nVerifique a conexão (o Tailscale está ligado?).';
          _loading = false;
        });
      }
    }
  }

  // Aparece so quando o servidor confirma que o e-mail nao foi verificado.
  // Silencio quando nao sabemos: alarmar por falha de rede treina o usuario a
  // ignorar o aviso, e ai ele nao serve para nada no dia em que importa.
  Widget? _avisoEmail() {
    final c = _conta;
    if (c == null || c['email_verified'] == true) return null;
    final email = (c['email'] ?? '').toString();
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      color: Colors.amber.shade50,
      child: ListTile(
        leading: Icon(Icons.warning_amber, color: Colors.amber.shade800),
        title: const Text('E-mail não confirmado'),
        subtitle: const Text(
            'Sem confirmar, não há como recuperar a conta se você esquecer a '
            'senha — e os dispositivos ficam presos a ela.'),
        isThreeLine: true,
        trailing: TextButton(
          onPressed: () async {
            await Navigator.push<bool>(
              context,
              MaterialPageRoute(builder: (_) => VerifyEmailPage(email: email)),
            );
            _load(); // volta e reavalia: pode ter sido confirmado agora
          },
          child: const Text('Confirmar'),
        ),
      ),
    );
  }

  Widget _errorView() => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 56, color: Colors.grey),
              const SizedBox(height: 16),
              Text(_error ?? 'Erro', textAlign: TextAlign.center),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final aviso = _avisoEmail();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Meus dispositivos'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: widget.onLogout, icon: const Icon(Icons.logout)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _errorView()
              : Column(children: [
                  ?aviso,
                  Expanded(
                    child: RefreshIndicator(
                      onRefresh: _load,
                      child: _devices.isEmpty
                          ? ListView(children: const [
                              Padding(
                                padding: EdgeInsets.all(32),
                                child: Center(
                                    child: Text('Nenhum dispositivo.\nAdicione um com o botão +',
                                        textAlign: TextAlign.center)),
                              )
                            ])
                          : ListView.builder(
                              itemCount: _devices.length,
                              itemBuilder: (_, i) {
                                final d = _devices[i] as Map<String, dynamic>;
                                final online = d['online'] == true;
                                final name = (d['name'] ?? d['device_id']).toString();
                                return Card(
                                  margin: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 6),
                                  child: ListTile(
                                    leading: Icon(Icons.videocam,
                                        color: online ? Colors.green : Colors.grey),
                                    title: Text(name),
                                    subtitle: Text(
                                        '${d['device_id']} · ${online ? 'online' : 'offline'}'),
                                    trailing: Icon(Icons.circle,
                                        size: 14,
                                        color: online ? Colors.green : Colors.red),
                                    onTap: () => Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (_) => DeviceDetailPage(
                                          token: widget.token,
                                          deviceId: d['device_id'].toString(),
                                          name: name,
                                        ),
                                      ),
                                    ),
                                  ),
                                );
                              },
                            ),
                          ),
                  ),
                ]),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => ClaimPage(token: widget.token)),
          );
          _load(); // atualiza a lista ao voltar (novo aparelho pode ter entrado)
        },
        icon: const Icon(Icons.add),
        label: const Text('Adicionar'),
      ),
    );
  }
}
