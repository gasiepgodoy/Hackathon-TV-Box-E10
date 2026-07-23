import 'package:flutter/material.dart';
import 'api.dart';
import 'config.dart';
import 'playback_page.dart';
import 'recording_window_page.dart';

// Lista os trechos gravados no cartão (via playback do MediaMTX).
class RecordingsPage extends StatefulWidget {
  const RecordingsPage({super.key});
  @override
  State<RecordingsPage> createState() => _RecordingsPageState();
}

class _RecordingsPageState extends State<RecordingsPage> {
  List<dynamic> _recs = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final r = await ApiService.recordings();
    if (mounted) {
      setState(() {
        _recs = r;
        _loading = false;
      });
    }
  }

  String _fmtStart(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      String two(int n) => n.toString().padLeft(2, '0');
      return '${two(dt.day)}/${two(dt.month)} ${two(dt.hour)}:${two(dt.minute)}';
    } catch (_) {
      return iso;
    }
  }

  String _clipUrl(String startIso, int durationSec) {
    return Uri.parse('$clipBase/clip').replace(queryParameters: {
      'start': DateTime.parse(startIso).toUtc().toIso8601String(),
      'duration': durationSec.toString(),
    }).toString();
  }

  String _fmtDur(num s) {
    final d = Duration(seconds: s.round());
    final h = d.inHours, m = d.inMinutes % 60, sec = d.inSeconds % 60;
    if (h > 0) return '${h}h ${m}min';
    if (m > 0) return '${m}min ${sec}s';
    return '${sec}s';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Gravações'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _recs.isEmpty
              ? const Center(child: Text('Nenhuma gravação'))
              : ListView.builder(
                  itemCount: _recs.length,
                  itemBuilder: (_, i) {
                    final r = _recs[i] as Map<String, dynamic>;
                    final start = r['start']?.toString() ?? '';
                    final dur = (r['duration'] is num) ? r['duration'] as num : 0;
                    return Card(
                      margin: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 6),
                      child: ListTile(
                        leading: const Icon(Icons.play_circle_outline),
                        title: Text(_fmtStart(start)),
                        subtitle: Text('duração: ${_fmtDur(dur)}'),
                        onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => dur <= 120
                                // trecho curto: toca direto (remuxado)
                                ? PlaybackPage(
                                    url: _clipUrl(start, dur.round()),
                                    title: _fmtStart(start))
                                // trecho longo: escolhe a janela
                                : RecordingWindowPage(
                                    startIso: start, spanDuration: dur),
                          ),
                        ),
                      ),
                    );
                  },
                ),
    );
  }
}
