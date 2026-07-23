import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';
import 'config.dart';
import 'api.dart';
import 'camera_page.dart';

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
  MqttServerClient? client;
  String connState = 'conectando...';
  bool deviceOnline = false;
  List<dynamic> events = [];

  @override
  void initState() {
    super.initState();
    _connect();
    _loadEvents();
  }

  Future<void> _loadEvents() async {
    final e = await ApiService.events(widget.token, widget.deviceId);
    if (mounted) setState(() => events = e);
  }

  Future<void> _connect() async {
    final clientId = 'app-${DateTime.now().millisecondsSinceEpoch}';
    final c = MqttServerClient(brokerHost, clientId);
    c.port = brokerPort;
    c.keepAlivePeriod = 30;
    c.autoReconnect = true;
    c.logging(on: false);
    c.onConnected = () => setState(() => connState = 'conectado');
    c.onDisconnected = () => setState(() => connState = 'desconectado');
    c.connectionMessage = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .authenticateAs(brokerUser, brokerPass)
        .startClean();
    client = c;
    try {
      await c.connect();
    } catch (e) {
      setState(() => connState = 'erro de conexão');
      c.disconnect();
      return;
    }
    c.subscribe('devices/${widget.deviceId}/#', MqttQos.atLeastOnce);
    c.updates?.listen(_onMessage);
  }

  void _onMessage(List<MqttReceivedMessage<MqttMessage>> msgs) {
    for (final m in msgs) {
      final topic = m.topic;
      final rec = m.payload as MqttPublishMessage;
      final payload =
          MqttPublishPayload.bytesToStringAsString(rec.payload.message);
      Map<String, dynamic> data = {};
      try {
        data = jsonDecode(payload) as Map<String, dynamic>;
      } catch (_) {}
      setState(() {
        if (topic.endsWith('/status')) {
          deviceOnline = data['online'] == true;
        } else if (topic.endsWith('/heartbeat')) {
          deviceOnline = true;
        } else if (topic.contains('/event')) {
          _loadEvents();
        }
      });
    }
  }

  void _sendSnapshot() {
    final c = client;
    if (c == null) return;
    final b = MqttClientPayloadBuilder();
    b.addString(jsonEncode({'action': 'snapshot'}));
    c.publishMessage('devices/${widget.deviceId}/camera/command',
        MqttQos.atLeastOnce, b.payload!);
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Comando snapshot enviado')));
  }

  @override
  Widget build(BuildContext context) {
    final connected = connState == 'conectado';
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
              Text('broker: $connState',
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
                  onPressed: connected ? _sendSnapshot : null,
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
              onRefresh: _loadEvents,
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

  @override
  void dispose() {
    client?.disconnect();
    super.dispose();
  }
}
