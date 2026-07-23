import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:wifi_scan/wifi_scan.dart';
import 'api.dart';

// Gera o token de claim e mostra o QR pra câmera do equipamento ler.
// Opcionalmente inclui Wi-Fi (ssid+senha) — o SSID pode ser buscado das redes
// próximas (a senha é sempre digitada; o Android não a fornece).
class ClaimPage extends StatefulWidget {
  final String token;
  const ClaimPage({super.key, required this.token});
  @override
  State<ClaimPage> createState() => _ClaimPageState();
}

class _ClaimPageState extends State<ClaimPage> {
  String? _claimToken;
  String? _error;
  bool _scanning = false;
  final _ssid = TextEditingController();
  final _pass = TextEditingController();

  @override
  void initState() {
    super.initState();
    _generate();
  }

  Future<void> _generate() async {
    setState(() {
      _claimToken = null;
      _error = null;
    });
    final res = await ApiService.claimToken(widget.token);
    if (res != null && res['token'] != null) {
      setState(() => _claimToken = res['token'].toString());
    } else {
      setState(() => _error = 'Não foi possível gerar o código');
    }
  }

  void _snack(String m) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));
    }
  }

  Future<void> _scanWifi() async {
    setState(() => _scanning = true);
    try {
      final can = await WiFiScan.instance.canStartScan();
      if (can != CanStartScan.yes) {
        _snack('Ative a localização/GPS e conceda a permissão pra buscar redes.');
        return;
      }
      await WiFiScan.instance.startScan();
      await Future.delayed(const Duration(seconds: 2));
      if (await WiFiScan.instance.canGetScannedResults() !=
          CanGetScannedResults.yes) {
        _snack('Sem permissão pra ler as redes.');
        return;
      }
      final results = await WiFiScan.instance.getScannedResults();
      final ssids = results
          .map((e) => e.ssid)
          .where((s) => s.trim().isNotEmpty)
          .toSet()
          .toList()
        ..sort();
      if (!mounted) return;
      if (ssids.isEmpty) {
        _snack('Nenhuma rede encontrada.');
        return;
      }
      final chosen = await showModalBottomSheet<String>(
        context: context,
        builder: (_) => SafeArea(
          child: ListView(
            shrinkWrap: true,
            children: [
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Redes próximas',
                    style: TextStyle(fontWeight: FontWeight.w500)),
              ),
              ...ssids.map((s) => ListTile(
                    leading: const Icon(Icons.wifi),
                    title: Text(s),
                    onTap: () => Navigator.pop(context, s),
                  )),
            ],
          ),
        ),
      );
      if (chosen != null) setState(() => _ssid.text = chosen);
    } catch (_) {
      _snack('Erro ao escanear redes.');
    } finally {
      if (mounted) setState(() => _scanning = false);
    }
  }

  String get _qrData {
    final m = <String, dynamic>{'token': _claimToken};
    if (_ssid.text.trim().isNotEmpty) {
      m['ssid'] = _ssid.text.trim();
      m['pass'] = _pass.text;
    }
    return jsonEncode(m);
  }

  @override
  void dispose() {
    _ssid.dispose();
    _pass.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Adicionar dispositivo')),
      body: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                    const SizedBox(height: 16),
                    FilledButton(
                        onPressed: _generate,
                        child: const Text('Tentar de novo')),
                  ],
                ),
              ),
            )
          : _claimToken == null
              ? const Center(child: CircularProgressIndicator())
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    children: [
                      const Text(
                        'Se o equipamento ainda não está numa rede, informe o Wi-Fi que ele deve usar. Se já está online, deixe em branco.',
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _ssid,
                              decoration: const InputDecoration(
                                labelText: 'Rede Wi-Fi (SSID) — opcional',
                                border: OutlineInputBorder(),
                                isDense: true,
                              ),
                              onChanged: (_) => setState(() {}),
                            ),
                          ),
                          const SizedBox(width: 8),
                          IconButton.filledTonal(
                            onPressed: _scanning ? null : _scanWifi,
                            tooltip: 'Buscar redes próximas',
                            icon: _scanning
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2))
                                : const Icon(Icons.wifi_find),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _pass,
                        decoration: const InputDecoration(
                          labelText: 'Senha do Wi-Fi',
                          border: OutlineInputBorder(),
                          isDense: true,
                        ),
                        obscureText: true,
                        onChanged: (_) => setState(() {}),
                      ),
                      const SizedBox(height: 24),
                      const Text(
                        'Aponte a câmera do equipamento para este código',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 16),
                      ),
                      const SizedBox(height: 16),
                      Container(
                        padding: const EdgeInsets.all(16),
                        color: Colors.white,
                        child: QrImageView(
                          data: _qrData,
                          size: 240,
                          backgroundColor: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 12),
                      const Text('O código expira em 15 minutos.',
                          style: TextStyle(color: Colors.grey)),
                      const SizedBox(height: 20),
                      OutlinedButton.icon(
                        onPressed: () => Navigator.pop(context),
                        icon: const Icon(Icons.check),
                        label: const Text('Concluído'),
                      ),
                    ],
                  ),
                ),
    );
  }
}
