import 'package:flutter/material.dart';
import 'api.dart';

// Configuração das câmeras: qualidade e por quanto tempo guardar a gravação.
// A cada ajuste mostra quanto espaço a escolha exige e se cabe no cartão.
class CameraSettingsPage extends StatefulWidget {
  // Token de mídia da box; sem ele a 9997 responde 401.
  final String? token;
  const CameraSettingsPage({super.key, this.token});

  @override
  State<CameraSettingsPage> createState() => _CameraSettingsPageState();
}

class _CameraSettingsPageState extends State<CameraSettingsPage> {
  static const List<int> _retentions = [6, 12, 24, 48, 72, 168];
  static const List<String> _qualities = ['baixa', 'media', 'alta'];
  static const Map<String, String> _qualityLabel = {
    'baixa': 'Baixa',
    'media': 'Média',
    'alta': 'Alta',
  };

  bool _loading = true;
  bool _saving = false;
  String? _error;
  List<Map<String, dynamic>> _cams = [];
  Map<String, dynamic> _presets = {};
  Map<String, dynamic> _storage = {};
  final Map<String, Map<String, dynamic>> _edit = {}; // id -> preferências
  final Map<String, Map<String, dynamic>> _orig = {};
  Map<String, bool> _notify = {};
  Map<String, bool> _origNotify = {};
  List<String> _sensitivities = ['baixa', 'media', 'alta'];
  List<int> _fpsOptions = [3, 5, 10, 15];
  List<String> _recordModes = ['continuo', 'movimento'];
  // O que a box mediu sobre o descarte, indexado pelo path do MediaMTX.
  Map<String, dynamic> _prune = {};
  final Map<String, String> _camPath = {}; // id da camera -> path
  double _cpuPerMpps = 8.3;

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
    final c = await ApiService.cameras(widget.token);
    final s = await ApiService.storage(widget.token);
    if (!mounted) return;
    if (c == null || s == null) {
      setState(() {
        _loading = false;
        _error = 'Não foi possível falar com a TV box.';
      });
      return;
    }
    final cams = (c['cameras'] as List? ?? [])
        .map((e) => (e as Map).cast<String, dynamic>())
        .toList();
    _edit.clear();
    _orig.clear();
    for (final cam in cams) {
      final id = cam['id']?.toString() ?? cam['path'].toString();
      final v = {
        'quality': cam['quality']?.toString() ?? 'media',
        'retention_h': (cam['retention_h'] as num? ?? 24).toInt(),
        'motion': cam['motion'] as bool? ?? true,
        'sensitivity': cam['sensitivity']?.toString() ?? 'media',
        'fps': (cam['fps'] as num? ?? 10).toInt(),
        // O PEDIDO, nao o que esta em vigor: uma camera com detecção desligada
        // tem o modo rebaixado para contínuo pela box, e a escolha do usuário
        // não pode se perder por causa disso.
        'record_mode':
            cam['record_mode_pedido']?.toString() ?? cam['record_mode']?.toString() ?? 'continuo',
      };
      _camPath[id] = cam['path']?.toString() ?? id;
      _edit[id] = Map.of(v);
      _orig[id] = Map.of(v);
    }
    final n = (c['notify'] as Map?) ?? {};
    setState(() {
      _cams = cams;
      _presets = (c['presets'] as Map?)?.cast<String, dynamic>() ?? {};
      _sensitivities = ((c['sensitivities'] as List?) ?? _sensitivities)
          .map((e) => e.toString())
          .toList();
      _fpsOptions = ((c['fps_options'] as List?) ?? _fpsOptions)
          .map((e) => (e as num).toInt())
          .toList();
      _cpuPerMpps = (c['cpu_per_mpps'] as num? ?? _cpuPerMpps).toDouble();
      _recordModes = ((c['record_modes'] as List?) ?? _recordModes)
          .map((e) => e.toString())
          .toList();
      _prune = (s['prune'] as Map?)?.cast<String, dynamic>() ?? {};
      _notify = {
        'motion': n['motion'] as bool? ?? true,
        'camera_offline': n['camera_offline'] as bool? ?? true,
      };
      _origNotify = Map.of(_notify);
      _storage = s;
      _loading = false;
    });
  }

  int _kbps(String quality) =>
      ((_presets[quality] as Map?)?['kbps'] as num? ?? 1000).toInt();

  String _sizeOf(String quality) =>
      (_presets[quality] as Map?)?['size']?.toString() ?? '';

  int _presetFps(String quality) =>
      ((_presets[quality] as Map?)?['fps'] as num? ?? 15).toInt();

  double get _cpuLoad => (_storage['load'] as num? ?? 0).toDouble();
  int get _cpus => (_storage['cpus'] as num? ?? 4).toInt();

  // Custo estimado de codificação: proporcional a pixels por segundo. A
  // constante vem da medição real feita neste equipamento.
  double _cpuOf(String id) {
    final e = _edit[id]!;
    final size = _sizeOf(e['quality'] as String).split('x');
    if (size.length != 2) return 0;
    final px = (int.tryParse(size[0]) ?? 0) * (int.tryParse(size[1]) ?? 0);
    final fps = (e['fps'] as num? ?? _presetFps(e['quality'] as String)).toInt();
    return px * fps / 1e6 * _cpuPerMpps;
  }

  double get _cpuTotal => _edit.keys.fold(0.0, (a, id) => a + _cpuOf(id));

  // Fração do tempo vigiado que sobrevive ao descarte, medida pela própria
  // box. Só vale com pelo menos uma hora observada: com dez minutos, um único
  // movimento distorceria a conta para qualquer lado.
  double? _ratio(String id) {
    final p = _prune[_camPath[id]] as Map?;
    if (p == null) return null;
    final vigiado = (p['vigiado_h'] as num? ?? 0).toDouble();
    final r = p['razao'];
    if (vigiado < 1 || r is! num) return null;
    return r.toDouble();
  }

  double _liberado(String id) =>
      ((_prune[_camPath[id]] as Map?)?['liberado_bytes'] as num? ?? 0).toDouble();

  bool _porMovimento(String id) => _edit[id]!['record_mode'] == 'movimento';

  // A detecção precisa estar ligada nos dois níveis: sem detector não há como
  // saber o que descartar, e a box rebaixa o modo para contínuo.
  bool _detectando(String id) =>
      (_edit[id]!['motion'] as bool? ?? true) && (_notify['motion'] ?? true);

  // Espaço que a retenção pedida exige: bitrate × tempo. Gravando só com
  // movimento, o que fica é uma fração disso — e usar a fração MEDIDA é o que
  // impede a tela de assustar com um número que não vai acontecer.
  double _needBytes(String id) {
    final e = _edit[id]!;
    final bruto = _kbps(e['quality'] as String) *
        1000 /
        8 *
        3600 *
        (e['retention_h'] as int);
    if (!_porMovimento(id) || !_detectando(id)) return bruto;
    return bruto * (_ratio(id) ?? 1.0); // sem medida ainda: assume o pior caso
  }

  double get _needTotal =>
      _edit.keys.fold(0.0, (a, id) => a + _needBytes(id));
  int get _kbpsTotal =>
      _edit.values.fold(0, (a, e) => a + _kbps(e['quality'] as String));
  double get _budget => (_storage['budget'] as num? ?? 0).toDouble();
  double get _autonomyH =>
      _kbpsTotal == 0 ? 0 : _budget * 8 / (_kbpsTotal * 1000) / 3600;
  bool get _dirty =>
      _edit.keys.any((id) => _edit[id].toString() != _orig[id].toString()) ||
      _notify.toString() != _origNotify.toString();

  String _recordHint(String id) {
    if (!_porMovimento(id)) {
      return 'Guarda tudo o que a câmera vê. O espaço é previsível e constante.';
    }
    if (!_detectando(id)) {
      return 'Precisa da detecção de movimento ligada, aqui e em Notificações. '
          'Sem detector não há como saber o que descartar, e a TV box continua '
          'guardando tudo.';
    }
    final r = _ratio(id);
    if (r == null) {
      return 'A câmera grava sempre, e a TV box descarta depois os trechos em '
          'que nada aconteceu — guardando 30 s antes e 60 s depois de cada '
          'movimento. Ainda medindo quanto isso economiza aqui.';
    }
    final lib = _liberado(id);
    final extra = lib > 0 ? ' — já liberou ${_gb(lib)}' : '';
    return 'Guardando ${(r * 100).round()}% do tempo vigiado$extra. Cada trecho '
        'mantém 30 s antes e 60 s depois do movimento.';
  }

  double get _liberadoTotal =>
      _edit.keys.fold(0.0, (a, id) => a + _liberado(id));

  String _gb(num b) => '${(b / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  String _hours(double h) =>
      h >= 48 ? '${(h / 24).toStringAsFixed(1)} dias' : '${h.toStringAsFixed(1)} h';
  String _retLabel(int h) => h >= 168 ? '7 dias' : (h >= 48 ? '${h ~/ 24} dias' : '${h}h');

  Future<void> _save() async {
    setState(() => _saving = true);
    final ok =
        await ApiService.saveSettings(
            {'cameras': _edit, 'notify': _notify}, widget.token);
    if (!mounted) return;
    setState(() => _saving = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(ok
          ? 'Configuração aplicada (a captura reiniciou).'
          : 'Não foi possível aplicar a configuração.'),
    ));
    if (ok) await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Câmeras e armazenamento'),
        actions: [
          IconButton(
              onPressed: _loading ? null : _load,
              icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: 12),
                    FilledButton(
                        onPressed: _load, child: const Text('Tentar novamente')),
                  ]),
                )
              : ListView(
                  padding: const EdgeInsets.all(12),
                  children: [
                    if (_cpuLoad > _cpus) _loadWarning(),
                    _summary(),
                    const SizedBox(height: 8),
                    _notifyCard(),
                    const SizedBox(height: 8),
                    for (final cam in _cams) _cameraCard(cam),
                  ],
                ),
      bottomNavigationBar: (_loading || _error != null)
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                child: FilledButton.icon(
                  onPressed: (!_dirty || _saving) ? null : _save,
                  icon: _saving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.save),
                  label: Text(_saving ? 'Aplicando...' : 'Aplicar'),
                ),
              ),
            ),
    );
  }

  Widget _summary() {
    final fits = _needTotal <= _budget;
    final per = (_storage['per_camera'] as Map?) ?? {};
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Armazenamento',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 10),
          _row('Espaço para gravação', _gb(_budget)),
          _row('Em uso agora',
              _gb((_storage['rec_used'] as num? ?? 0).toDouble())),
          for (final e in per.entries)
            _row('   ${e.key}', _gb((e.value as num).toDouble()), dim: true),
          if (_liberadoTotal > 0)
            _row('Já liberado pelo descarte', _gb(_liberadoTotal)),
          const Divider(height: 20),
          _row('Consumo somado', '${(_kbpsTotal / 1000).toStringAsFixed(1)} Mbps'),
          _row('Retenção pedida', _gb(_needTotal)),
          _row('Processador (estimado)',
              '${_cpuTotal.round()}% de ${_cpus * 100}%'),
          const SizedBox(height: 10),
          _banner(
              fits,
              fits
                  ? 'Cabe. Sobram ${_gb(_budget - _needTotal)} de folga.'
                  : 'Não cabe: faltam ${_gb(_needTotal - _budget)}. As gravações '
                      'mais antigas serão apagadas antes de completar a retenção — '
                      'na prática a TV box guarda ~${_hours(_autonomyH)}.'),
          const SizedBox(height: 8),
          _banner(
              _cpuTotal <= _cpus * 75,
              _cpuTotal <= _cpus * 75
                  ? 'Processamento folgado para a captura.'
                  : 'Processamento apertado: a captura pode atrasar e o replay '
                      'ficar lento. Reduza os quadros por segundo ou a qualidade '
                      'de uma câmera.'),
        ]),
      ),
    );
  }

  // A TV box não tem codificador por hardware: cada câmera é comprimida por
  // software. Passando da capacidade, a captura atrasa e o replay fica lento.
  Widget _loadWarning() => Card(
        color: Colors.orange.withValues(alpha: 0.15),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            const Icon(Icons.memory, color: Colors.orange),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Processador no limite (carga ${_cpuLoad.toStringAsFixed(1)} para '
                '$_cpus núcleos). Reduza a qualidade de uma câmera para o vídeo '
                'e o replay voltarem a ficar fluidos.',
                style: const TextStyle(fontSize: 13),
              ),
            ),
          ]),
        ),
      );

  Widget _notifyCard() => Card(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 4),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Notificações',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const Text(
                'Desligado aqui, o alerta nem chega a ser enviado pela TV box.',
                style: TextStyle(color: Colors.grey, fontSize: 12)),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Movimento'),
              subtitle: const Text('Quando alguma câmera detecta movimento'),
              value: _notify['motion'] ?? true,
              onChanged: (v) => setState(() => _notify['motion'] = v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Câmera desconectada'),
              subtitle: const Text('Quando uma câmera cai ou volta'),
              value: _notify['camera_offline'] ?? true,
              onChanged: (v) => setState(() => _notify['camera_offline'] = v),
            ),
          ]),
        ),
      );

  Widget _banner(bool ok, String text) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: (ok ? Colors.green : Colors.orange).withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(children: [
          Icon(ok ? Icons.check_circle : Icons.warning_amber,
              color: ok ? Colors.green : Colors.orange, size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ]),
      );

  Widget _row(String k, String v, {bool dim = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          Expanded(
              child: Text(k,
                  style: TextStyle(color: dim ? Colors.grey : null, fontSize: 13))),
          Text(v,
              style: TextStyle(
                  color: dim ? Colors.grey : null,
                  fontSize: 13,
                  fontWeight: dim ? null : FontWeight.w500)),
        ]),
      );

  Widget _cameraCard(Map<String, dynamic> cam) {
    final id = cam['id']?.toString() ?? cam['path'].toString();
    final e = _edit[id]!;
    final q = e['quality'] as String;
    final ret = e['retention_h'] as int;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(cam['name']?.toString() ?? 'Câmera',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          Text(cam['label']?.toString() ?? '',
              style: const TextStyle(color: Colors.grey, fontSize: 12)),
          const SizedBox(height: 12),
          const Text('Qualidade', style: TextStyle(fontSize: 13)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              for (final k in _qualities)
                ChoiceChip(
                  label: Text(
                      '${_qualityLabel[k]} · ${(_kbps(k) / 1000).toStringAsFixed(1)} Mbps'),
                  selected: q == k,
                  onSelected: (_) => setState(() => e['quality'] = k),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text('${_sizeOf(q)} · ${_gb(_needBytes(id))} para ${_retLabel(ret)}'
              '${_porMovimento(id) && _detectando(id) ? " (só o movimento)" : ""}',
              style: const TextStyle(color: Colors.grey, fontSize: 12)),
          const SizedBox(height: 12),
          Row(children: [
            const Text('Quadros por segundo', style: TextStyle(fontSize: 13)),
            const Spacer(),
            Text('~${_cpuOf(id).round()}% de CPU',
                style: const TextStyle(color: Colors.grey, fontSize: 12)),
          ]),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              for (final f in _fpsOptions)
                ChoiceChip(
                  label: Text('$f fps'),
                  selected: (e['fps'] as int? ?? 10) == f,
                  onSelected: (_) => setState(() => e['fps'] = f),
                ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
              'É o que mais pesa no processador. Em vigilância, 5 fps já '
              'costuma bastar.',
              style: TextStyle(color: Colors.grey, fontSize: 12)),
          const SizedBox(height: 12),
          const Text('Guardar por', style: TextStyle(fontSize: 13)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              for (final h in _retentions)
                ChoiceChip(
                  label: Text(_retLabel(h)),
                  selected: ret == h,
                  onSelected: (_) => setState(() => e['retention_h'] = h),
                ),
            ],
          ),
          const SizedBox(height: 12),
          const Text('Gravar', style: TextStyle(fontSize: 13)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            children: [
              if (_recordModes.contains('continuo'))
                ChoiceChip(
                  label: const Text('Sempre'),
                  selected: !_porMovimento(id),
                  onSelected: (_) =>
                      setState(() => e['record_mode'] = 'continuo'),
                ),
              if (_recordModes.contains('movimento'))
                ChoiceChip(
                  label: const Text('Só com movimento'),
                  selected: _porMovimento(id),
                  // Desligado quando não há detector: o modo seria rebaixado
                  // pela box de qualquer forma, e um botão que não faz o que
                  // diz é pior que um botão ausente.
                  onSelected: _detectando(id)
                      ? (_) => setState(() => e['record_mode'] = 'movimento')
                      : null,
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(_recordHint(id),
              style: const TextStyle(color: Colors.grey, fontSize: 12)),
          const Divider(height: 24),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: const Text('Detectar movimento'),
            value: e['motion'] as bool? ?? true,
            onChanged: (_notify['motion'] ?? true)
                ? (v) => setState(() => e['motion'] = v)
                : null, // notificação de movimento está desligada no geral
          ),
          if ((e['motion'] as bool? ?? true) && (_notify['motion'] ?? true)) ...[
            const Text('Sensibilidade', style: TextStyle(fontSize: 13)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 8,
              children: [
                for (final s in _sensitivities)
                  ChoiceChip(
                    label: Text(_qualityLabel[s] ?? s),
                    selected: (e['sensitivity'] as String? ?? 'media') == s,
                    onSelected: (_) => setState(() => e['sensitivity'] = s),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            const Text(
                'Alta dispara com pouco movimento; baixa evita alarme falso.',
                style: TextStyle(color: Colors.grey, fontSize: 12)),
          ],
        ]),
      ),
    );
  }
}
