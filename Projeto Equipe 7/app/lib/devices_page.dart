import 'package:flutter/material.dart';
import 'api.dart';
import 'device_detail_page.dart';
import 'claim_page.dart';

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
      if (mounted) {
        setState(() {
          _devices = d;
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
              : RefreshIndicator(
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
