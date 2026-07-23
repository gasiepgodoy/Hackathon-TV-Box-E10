import 'package:flutter/material.dart';
import 'config.dart';
import 'playback_page.dart';

// Escolhe uma janela (horário + duração) dentro de um trecho contínuo e reproduz
// só essa fatia (o MediaMTX aceita start + duration no /get).
class RecordingWindowPage extends StatefulWidget {
  final String startIso; // início do trecho contínuo
  final num spanDuration; // duração total do trecho (s)
  const RecordingWindowPage({
    super.key,
    required this.startIso,
    required this.spanDuration,
  });
  @override
  State<RecordingWindowPage> createState() => _RecordingWindowPageState();
}

class _RecordingWindowPageState extends State<RecordingWindowPage> {
  double _offset = 0; // segundos a partir do início do trecho
  int _windowMin = 5;

  List<int> get _windowOptions {
    final maxMin = (widget.spanDuration / 60).floor();
    final opts = [1, 5, 15, 30].where((m) => m <= maxMin).toList();
    return opts.isEmpty ? [1] : opts;
  }

  DateTime get _startDt =>
      DateTime.parse(widget.startIso).add(Duration(seconds: _offset.round()));

  String _fmtTime(DateTime dt) {
    final l = dt.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(l.day)}/${two(l.month)} ${two(l.hour)}:${two(l.minute)}';
  }

  void _play() {
    final maxWindow =
        (widget.spanDuration - _offset).clamp(1, double.infinity).toInt();
    final windowSec = (_windowMin * 60).clamp(1, maxWindow);
    final url = Uri.parse('$clipBase/clip').replace(queryParameters: {
      'start': _startDt.toUtc().toIso8601String(),
      'duration': windowSec.toString(),
    }).toString();
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => PlaybackPage(url: url, title: _fmtTime(_startDt)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_windowOptions.contains(_windowMin)) _windowMin = _windowOptions.first;
    return Scaffold(
      appBar: AppBar(title: const Text('Escolher trecho')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Trecho: ${_fmtTime(DateTime.parse(widget.startIso))}  ·  ${(widget.spanDuration / 3600).toStringAsFixed(1)}h'),
            const SizedBox(height: 28),
            Text('Reproduzir a partir de:',
                style: Theme.of(context).textTheme.bodyMedium),
            Text(_fmtTime(_startDt),
                style: Theme.of(context).textTheme.headlineSmall),
            Slider(
              value: _offset,
              min: 0,
              max: widget.spanDuration.toDouble(),
              onChanged: (v) => setState(() => _offset = v),
            ),
            const SizedBox(height: 16),
            const Text('Duração:'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: _windowOptions
                  .map((m) => ChoiceChip(
                        label: Text('$m min'),
                        selected: _windowMin == m,
                        onSelected: (_) => setState(() => _windowMin = m),
                      ))
                  .toList(),
            ),
            const Spacer(),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _play,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Reproduzir trecho'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
