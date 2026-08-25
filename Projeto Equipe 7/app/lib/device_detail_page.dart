import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';
import 'camera_page.dart';

// Detalhe do dispositivo: presença, comando de snapshot e histórico.
//
// Esta tela já falou MQTT direto com o broker. Deixou de falar por um motivo de
// segurança: a credencial do broker vinha embutida no app, e qualquer pessoa
// que extraísse o APK poderia assinar `devices/#` e publicar comandos. Agora
// tudo passa pelo servidor, que confere a posse do aparelho — e o broker não
// precisa ser publicado na internet.
//
// O custo é a presença deixar de ser instantânea: em vez do heartbeat via MQTT,
// a tela consulta a API periodicamente. Para um pontinho de status, troca justa.
class DeviceDetailPage extends StatefulWidget {
  final String token;
  final String deviceId;
  final String name;
  const DeviceDetailPage({
    super.key,
    required this.token,
    required this.deviceId,
    required this.name,
  });
  @override
  State<DeviceDetailPage> createState() => _DeviceDetailPageState();
}

class _DeviceDetailPageState extends State<DeviceDetailPage> {
  static const Duration _intervalo = Duration(seconds: 10);

  bool deviceOnline = false;
  bool _semServidor = false;
  List<dynamic> events = [];
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _atualizar();
    _timer = Timer.periodic(_intervalo, (_) => _atualizar());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _atualizar() async {
    // A presença vem da mesma coluna que o Node-RED mantém a partir do status
    // e do heartbeat publicados pela box — só que lida por HTTPS.
    try {
      final lista = await ApiService.devices(widget.token);
      final d = lista.cast<Map<String, dynamic>>().firstWhere(
            (e) => e['device_id']?.toString() == widget.deviceId,
            orElse: () => <String, dynamic>{},
          );
      final e = await ApiService.events(widget.token, widget.deviceId);
      if (!mounted) return;
      setState(() {
        deviceOnline = d['online'] == true;
        events = e;
        _semServidor = false;
      });
    } catch (_) {
      // Falha de rede não deve virar "aparelho offline": são coisas diferentes,
      // e confundi-las faria o usuário procurar problema no lugar errado.
      if (mounted) setState(() => _semServidor = true);
    }
  }

  Future<void> _sendSnapshot() async {
    final ok = await ApiService.command(
        widget.token, widget.deviceId, 'camera', 'snapshot');
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok
            ? 'Comando snapshot enviado'
            : 'Não foi possível enviar o comando')));
    if (ok) _atualizar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.name)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Icon(Icons.circle,
                  size: 14, color: deviceOnline ? Colors.green : Colors.red),
              const SizedBox(width: 8),
              Text(deviceOnline ? 'online' : 'offline'),
              const Spacer(),
              if (_semServidor)
                Text('sem contato com o servidor',
                    style: Theme.of(context).textTheme.bodySmall),
            ]),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => CameraPage(
                            name: widget.name,
                            token: widget.token,
                            deviceId: widget.deviceId)),
                  ),
                  icon: const Icon(Icons.videocam),
                  label: const Text('Câmera'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  onPressed: deviceOnline ? _sendSnapshot : null,
                  icon: const Icon(Icons.camera_alt),
                  label: const Text('Snapshot'),
                ),
              ),
            ]),
          ),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 20, 16, 8),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text('Eventos recentes',
                  style: TextStyle(fontWeight: FontWeight.w500)),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _atualizar,
              child: events.isEmpty
                  ? ListView(children: const [
                      Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(child: Text('Sem eventos ainda')),
                      )
                    ])
                  : ListView.builder(
                      itemCount: events.length,
                      itemBuilder: (_, i) {
                        final e = events[i] as Map<String, dynamic>;
                        return ListTile(
                          dense: true,
                          leading: const Icon(Icons.bolt, size: 18),
                          title: Text('${e['module']}: ${e['type']}'),
                          subtitle: Text('${e['created_at']}'),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
