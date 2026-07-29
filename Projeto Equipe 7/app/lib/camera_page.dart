import 'dart:async';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';
import 'config.dart';
import 'api.dart';
import 'live_view.dart';
import 'camera_settings_page.dart';

class _Span {
  final DateTime start;
  final DateTime end;
  _Span(this.start, this.end);
}

// Tela unificada: ao vivo + gravações numa régua de tempo (por data).
class CameraPage extends StatefulWidget {
  final String name;
  final String token;
  final String deviceId;
  const CameraPage({
    super.key,
    required this.name,
    required this.token,
    required this.deviceId,
  });
  @override
  State<CameraPage> createState() => _CameraPageState();
}

class _CameraPageState extends State<CameraPage> {
  double _pxPerSec = 0.5; // 1px = 2s (ajustável com zoom)
  static const int chunkSec = 60; // trechos de 1 min

  List<_Span> _spans = [];
  DateTime _rangeStart = DateTime.now().subtract(const Duration(hours: 1));
  DateTime _rangeEnd = DateTime.now();
  bool _loadingList = true;
  List<DateTime> _motionMarks = [];
  Timer? _eventTimer;
  int _camIndex = 0;
  List<CamInfo> _cams = cameras; // fallback; substituído pela lista da TV box
  int _connected = 0;
  int _limit = 0;
  bool _exceeded = false;
  CamInfo get _cam => _cams[_camIndex.clamp(0, _cams.length - 1)];

  bool _live = true;
  VideoPlayerController? _video;
  ChewieController? _chewie;
  DateTime? _chunkStart;
  String _status = '';
  bool _loadingNext = false;
  double _speed = 1.0; // velocidade do replay (mantida entre trechos)
  // Trecho seguinte já aberto em segundo plano (virada sem pausa).
  VideoPlayerController? _preCtl;
  DateTime? _preStart;
  Future<VideoPlayerController?>? _preJob;

  final ScrollController _scroll = ScrollController();
  bool _userDragging = false;
  double _viewWidth = 300;

  @override
  void initState() {
    super.initState();
    _loadCameras();
    _loadEvents();
    _eventTimer =
        Timer.periodic(const Duration(seconds: 30), (_) => _loadEvents());
  }

  Future<void> _loadCameras() async {
    final data = await ApiService.cameras();
    if (data != null &&
        data['cameras'] is List &&
        (data['cameras'] as List).isNotEmpty) {
      final list = (data['cameras'] as List).map((e) {
        final m = e as Map<String, dynamic>;
        return CamInfo(m['name']?.toString() ?? 'Câmera',
            m['path']?.toString() ?? 'cam');
      }).toList();
      if (mounted) {
        setState(() {
          _cams = list;
          _connected = (data['connected'] as num?)?.toInt() ?? list.length;
          _limit = (data['limit'] as num?)?.toInt() ?? list.length;
          _exceeded = data['exceeded'] == true;
          if (_camIndex >= _cams.length) _camIndex = 0;
        });
      }
    }
    _loadList();
  }

  Future<void> _loadEvents() async {
    final evs = await ApiService.events(widget.token, widget.deviceId);
    final marks = <DateTime>[];
    for (final e in evs) {
      final m = e as Map<String, dynamic>;
      if (m['module'] == 'alarme') {
        final t = DateTime.tryParse(m['created_at']?.toString() ?? '');
        if (t != null) marks.add(t);
      }
    }
    if (mounted) setState(() => _motionMarks = marks);
  }

  Future<void> _loadList() async {
    final list = await ApiService.recordings(_cam.path);
    final spans = <_Span>[];
    for (final r in list) {
      final m = r as Map<String, dynamic>;
      final st = DateTime.tryParse(m['start']?.toString() ?? '');
      final durNum = (m['duration'] is num) ? m['duration'] as num : 0;
      if (st != null) {
        spans.add(_Span(st, st.add(Duration(seconds: durNum.round()))));
      }
    }
    spans.sort((a, b) => a.start.compareTo(b.start));
    final now = DateTime.now();
    if (mounted) {
      setState(() {
        _spans = spans;
        _rangeStart =
            spans.isNotEmpty ? spans.first.start : now.subtract(const Duration(hours: 1));
        _rangeEnd = now;
        _loadingList = false;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
      });
    }
  }

  double _timeToOffset(DateTime t) =>
      t.difference(_rangeStart).inMilliseconds / 1000.0 * _pxPerSec;

  DateTime _offsetToTime(double off) =>
      _rangeStart.add(Duration(milliseconds: (off / _pxPerSec * 1000).round()));

  DateTime get _centerTime =>
      _scroll.hasClients ? _offsetToTime(_scroll.offset) : _rangeEnd;

  bool _isRecorded(DateTime t) =>
      _spans.any((s) => !t.isBefore(s.start) && t.isBefore(s.end));

  bool _onScroll(ScrollNotification n) {
    if (n is ScrollStartNotification && n.dragDetails != null) {
      _userDragging = true;
    } else if (n is ScrollUpdateNotification && _userDragging) {
      setState(() {}); // atualiza o rótulo de horário
    } else if (n is ScrollEndNotification && _userDragging) {
      _userDragging = false;
      _seekTo(_centerTime);
    }
    return false;
  }

  Future<void> _seekTo(DateTime t) async {
    if (_rangeEnd.difference(t).inSeconds < 15) {
      _goLive();
      return;
    }
    if (!_isRecorded(t)) {
      setState(() {
        _live = false;
        _status = 'sem gravação neste horário';
      });
      await _disposePlayer();
      return;
    }
    await _playChunk(t);
  }

  // Alinha um instante ao início do trecho na grade (minuto cheio). Sem isso,
  // trechos começariam onde o usuário clicou e se sobreporiam entre si.
  DateTime _snap(DateTime t) {
    const gridMs = chunkSec * 1000;
    final ms = t.millisecondsSinceEpoch;
    return DateTime.fromMillisecondsSinceEpoch(ms - ms % gridMs);
  }

  // Duração disponível do trecho que começa em [start].
  int _durFor(DateTime start) {
    final span = _spans.firstWhere(
        (s) => !start.isBefore(s.start) && start.isBefore(s.end),
        orElse: () => _Span(start, start.add(const Duration(seconds: chunkSec))));
    final avail = span.end.difference(start).inSeconds;
    return avail < chunkSec ? avail : chunkSec;
  }

  // Endereço do trecho no servidor da TV box.
  String _urlFor(DateTime start, int dur) =>
      Uri.parse('$clipBase/clip').replace(queryParameters: {
        'path': _cam.path,
        'start': start.toUtc().toIso8601String(),
        'duration': dur.toString(),
      }).toString();

  // Abre o trecho direto da rede: como o MP4 sai com +faststart, o player começa
  // com os primeiros KB e segue carregando, em vez de esperar o arquivo inteiro.
  Future<VideoPlayerController?> _openChunk(DateTime start, int dur) async {
    final v = VideoPlayerController.networkUrl(Uri.parse(_urlFor(start, dur)));
    try {
      await v.initialize();
      return v;
    } catch (_) {
      await v.dispose();
      return null;
    }
  }

  // Prepara o trecho seguinte enquanto o atual toca: ele já inicializa e vai
  // enchendo o buffer, então a virada não espera a rede.
  void _prefetch(DateTime raw) {
    final start = _snap(raw);
    if (_preStart == start) return;
    _dropPrefetch();
    final dur = _durFor(start);
    if (dur <= 1) return;
    _preStart = start;
    _preJob = _openChunk(start, dur).then((c) {
      _preCtl = c;
      _preJob = null;
      return c;
    });
  }

  String _speedLabel(double s) => s == s.roundToDouble()
      ? '${s.toInt()}x'
      : '${s.toString().replaceAll('.', ',')}x';

  void _setSpeed(double s) {
    setState(() => _speed = s);
    _video?.setPlaybackSpeed(s);
  }

  void _dropPrefetch() {
    _preCtl?.dispose();
    _preCtl = null;
    _preStart = null;
    _preJob = null;
  }

  // [target] é o horário desejado; o trecho carregado é o da grade que o contém
  // e o player pula para o ponto exato dentro dele.
  Future<void> _playChunk(DateTime target) async {
    final start = _snap(target);
    final seek = target.difference(start);
    final dur = _durFor(start);
    if (dur <= 1) {
      setState(() => _status = 'fim da gravação');
      return;
    }
    // Se este trecho já veio do prefetch, entra no ar sem esperar a rede.
    VideoPlayerController? v;
    if (_preStart == start) {
      final job = _preJob;
      if (job != null) {
        setState(() => _status = 'carregando...');
        v = await job;
      } else {
        v = _preCtl;
      }
      _preCtl = null;
      _preStart = null;
      _preJob = null;
    } else {
      _dropPrefetch();
    }
    await _disposePlayer();
    setState(() {
      _live = false;
      _status = v == null ? 'carregando...' : '';
      _chunkStart = start;
    });
    v ??= await _openChunk(start, dur);
    if (v == null) {
      if (mounted) setState(() => _status = 'erro ao carregar');
      return;
    }
    try {
      if (seek > Duration.zero && seek < v.value.duration) {
        await v.seekTo(seek);
      }
      await v.setPlaybackSpeed(_speed);
      final c = ChewieController(
        videoPlayerController: v,
        autoPlay: true,
        looping: false,
        showControls: false,
        aspectRatio: v.value.aspectRatio == 0 ? 16 / 9 : v.value.aspectRatio,
      );
      v.addListener(_onTick);
      if (mounted) {
        setState(() {
          _video = v;
          _chewie = c;
          _status = '';
        });
      }
    } catch (e) {
      if (mounted) setState(() => _status = 'erro ao carregar');
    }
  }

  void _onTick() {
    final v = _video;
    final cs = _chunkStart;
    if (v == null || cs == null || !v.value.isInitialized) return;
    final pos = v.value.position;
    // segue a régua com o horário tocando (sem mexer se o usuário arrasta)
    if (!_userDragging && _scroll.hasClients) {
      final off = _timeToOffset(cs.add(pos))
          .clamp(0.0, _scroll.position.maxScrollExtent);
      _scroll.jumpTo(off);
    }
    setState(() {});
    final dur = v.value.duration;
    if (_loadingNext || dur.inMilliseconds <= 0) return;
    // próximo trecho da grade (não a duração real do arquivo, que varia uns ms
    // e faria a emenda derivar/sobrepor)
    final next = cs.add(const Duration(seconds: chunkSec));
    if (!_isRecorded(next)) return;
    // adianta o download do próximo trecho antes do fim
    // (a antecedência acompanha a velocidade: em 4x sobra menos tempo real)
    final lead = Duration(seconds: (20 * _speed).round());
    if (pos >= dur - lead) _prefetch(next);
    // fim do trecho → troca (instantânea, se o prefetch já terminou)
    if (pos >= dur - const Duration(milliseconds: 400)) {
      _loadingNext = true;
      _playChunk(next).whenComplete(() => _loadingNext = false);
    }
  }

  void _goLive() {
    _dropPrefetch();
    _disposePlayer();
    setState(() {
      _live = true;
      _status = '';
    });
    if (_scroll.hasClients) {
      _scroll.jumpTo(_scroll.position.maxScrollExtent);
    }
  }

  Future<void> _disposePlayer() async {
    _video?.removeListener(_onTick);
    final c = _chewie;
    final v = _video;
    _chewie = null;
    _video = null;
    c?.dispose();
    await v?.dispose();
  }

  void _zoom(double factor) {
    final center = _centerTime;
    setState(() => _pxPerSec = (_pxPerSec * factor).clamp(0.05, 5.0));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        final off = _timeToOffset(center)
            .clamp(0.0, _scroll.position.maxScrollExtent);
        _scroll.jumpTo(off);
      }
    });
  }

  Widget _legendDot(Color c) => Container(width: 10, height: 10, color: c);

  void _switchCamera(int i) {
    if (i == _camIndex) return;
    _dropPrefetch();
    _disposePlayer();
    setState(() {
      _camIndex = i;
      _live = true;
      _loadingList = true;
      _motionMarks = [];
    });
    _loadList();
  }

  String _fmtDT(DateTime t) {
    final l = t.toLocal();
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(l.day)}/${two(l.month)} ${two(l.hour)}:${two(l.minute)}:${two(l.second)}';
  }

  @override
  Widget build(BuildContext context) {
    final label = _fmtDT(_centerTime);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(widget.name),
        actions: [
          if (_cams.length > 1)
            PopupMenuButton<int>(
              initialValue: _camIndex,
              onSelected: _switchCamera,
              itemBuilder: (_) => [
                for (int i = 0; i < _cams.length; i++)
                  PopupMenuItem(value: i, child: Text(_cams[i].name)),
              ],
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Text(_cam.name),
                  const Icon(Icons.arrow_drop_down),
                ]),
              ),
            ),
          IconButton(
            tooltip: 'Câmeras e armazenamento',
            icon: const Icon(Icons.settings),
            onPressed: () async {
              await Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => const CameraSettingsPage()));
              _loadCameras(); // a qualidade pode ter mudado
            },
          ),
        ],
      ),
      body: Column(
        children: [
          if (_exceeded)
            Container(
              width: double.infinity,
              color: Colors.orange.shade800,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(children: [
                const Icon(Icons.warning_amber, color: Colors.white, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '$_connected câmeras conectadas, mas só $_limit são suportadas — as extras não são transmitidas.',
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
              ]),
            ),
          // vídeo
          Expanded(
            child: Container(
              color: Colors.black,
              child: _live
                  ? LiveView(
                      key: ValueKey(_cam.path),
                      whepUrl: '$whepBase/${_cam.path}/whep')
                  : (_chewie != null
                      ? Chewie(controller: _chewie!)
                      : Center(
                          child: Text(
                              _status.isEmpty ? 'selecione um horário' : _status,
                              style: const TextStyle(color: Colors.white70)))),
            ),
          ),
          // barra de estado + botão ao vivo
          Container(
            color: const Color(0xFF111111),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                Icon(Icons.circle,
                    size: 12, color: _live ? Colors.red : Colors.white38),
                const SizedBox(width: 8),
                Text(_live ? 'AO VIVO' : label,
                    style: const TextStyle(color: Colors.white)),
                const Spacer(),
                if (!_live)
                  PopupMenuButton<double>(
                    tooltip: 'Velocidade',
                    initialValue: _speed,
                    onSelected: _setSpeed,
                    itemBuilder: (_) => [
                      for (final s in const [0.5, 1.0, 1.5, 2.0, 4.0])
                        PopupMenuItem(value: s, child: Text(_speedLabel(s))),
                    ],
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.speed,
                            size: 18, color: Colors.white70),
                        const SizedBox(width: 4),
                        Text(_speedLabel(_speed),
                            style: const TextStyle(color: Colors.white70)),
                      ]),
                    ),
                  ),
                TextButton.icon(
                  onPressed: _live ? null : _goLive,
                  icon: const Icon(Icons.sensors, size: 18),
                  label: const Text('Ao vivo'),
                ),
              ],
            ),
          ),
          // legenda + zoom
          Container(
            color: const Color(0xFF111111),
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(children: [
              _legendDot(const Color(0xFF3949AB)),
              const Text(' gravado   ',
                  style: TextStyle(color: Colors.white54, fontSize: 11)),
              _legendDot(const Color(0xFF444444)),
              const Text(' offline',
                  style: TextStyle(color: Colors.white54, fontSize: 11)),
              const Spacer(),
              IconButton(
                onPressed: () => _zoom(0.5),
                icon: const Icon(Icons.zoom_out, color: Colors.white70),
                visualDensity: VisualDensity.compact,
              ),
              IconButton(
                onPressed: () => _zoom(2.0),
                icon: const Icon(Icons.zoom_in, color: Colors.white70),
                visualDensity: VisualDensity.compact,
              ),
            ]),
          ),
          // régua de tempo
          _loadingList
              ? const SizedBox(
                  height: 74,
                  child: Center(
                      child: CircularProgressIndicator(color: Colors.white54)))
              : LayoutBuilder(builder: (ctx, c) {
                  _viewWidth = c.maxWidth;
                  final totalSec =
                      _rangeEnd.difference(_rangeStart).inSeconds.toDouble();
                  final contentW =
                      (totalSec * _pxPerSec).clamp(_viewWidth, double.infinity);
                  return SizedBox(
                    height: 74,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        NotificationListener<ScrollNotification>(
                          onNotification: _onScroll,
                          child: SingleChildScrollView(
                            controller: _scroll,
                            scrollDirection: Axis.horizontal,
                            child: Padding(
                              padding:
                                  EdgeInsets.symmetric(horizontal: _viewWidth / 2),
                              child: CustomPaint(
                                size: Size(contentW, 74),
                                painter: _RulerPainter(
                                    _rangeStart, _rangeEnd, _spans, _pxPerSec,
                                    _motionMarks),
                              ),
                            ),
                          ),
                        ),
                        IgnorePointer(
                          child: Container(
                              width: 2, height: 74, color: Colors.redAccent),
                        ),
                      ],
                    ),
                  );
                }),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _eventTimer?.cancel();
    _dropPrefetch();
    _disposePlayer();
    _scroll.dispose();
    super.dispose();
  }
}

class _RulerPainter extends CustomPainter {
  final DateTime rangeStart, rangeEnd;
  final List<_Span> spans;
  final double pxPerSec;
  final List<DateTime> marks;
  _RulerPainter(
      this.rangeStart, this.rangeEnd, this.spans, this.pxPerSec, this.marks);

  int _tickStep() {
    // passo que mantém ~1 rótulo a cada 70px, conforme o zoom
    const steps = [60, 300, 600, 1800, 3600, 10800, 21600, 43200, 86400];
    for (final s in steps) {
      if (s * pxPerSec >= 70) return s;
    }
    return 86400;
  }

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
        Offset.zero & size, Paint()..color = const Color(0xFF1E1E1E));
    final top = size.height * 0.5, bot = size.height * 0.8;
    final totalSec = rangeEnd.difference(rangeStart).inSeconds;
    // base: offline / sem gravação (cinza)
    canvas.drawRect(Rect.fromLTRB(0, top, totalSec * pxPerSec, bot),
        Paint()..color = const Color(0xFF444444));
    // trechos gravados (azul) por cima
    final rec = Paint()..color = const Color(0xFF3949AB);
    for (final s in spans) {
      final x1 =
          s.start.difference(rangeStart).inMilliseconds / 1000.0 * pxPerSec;
      final x2 =
          s.end.difference(rangeStart).inMilliseconds / 1000.0 * pxPerSec;
      canvas.drawRect(Rect.fromLTRB(x1, top, x2, bot), rec);
    }
    // ticks adaptativos, alinhados a horários redondos
    final tick = Paint()
      ..color = Colors.white24
      ..strokeWidth = 1;
    final step = _tickStep();
    final startEpoch = rangeStart.millisecondsSinceEpoch ~/ 1000;
    final endEpoch = startEpoch + totalSec;
    final first = ((startEpoch / step).ceil()) * step;
    for (int e = first; e <= endEpoch; e += step) {
      final x = (e - startEpoch) * pxPerSec;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height * 0.35), tick);
      final t = DateTime.fromMillisecondsSinceEpoch(e * 1000).toLocal();
      String two(int n) => n.toString().padLeft(2, '0');
      final label = step >= 86400
          ? '${two(t.day)}/${two(t.month)}'
          : '${two(t.hour)}:${two(t.minute)}';
      final tp = TextPainter(
        text: TextSpan(
            text: label,
            style: const TextStyle(color: Colors.white54, fontSize: 10)),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(x + 2, size.height * 0.36));
    }
    // marcadores de movimento (vermelho)
    final mkFill = Paint()..color = Colors.red;
    final mkLine = Paint()
      ..color = Colors.red
      ..strokeWidth = 2;
    for (final t in marks) {
      final x = t.difference(rangeStart).inMilliseconds / 1000.0 * pxPerSec;
      if (x < 0 || x > size.width) continue;
      canvas.drawLine(Offset(x, size.height * 0.42),
          Offset(x, size.height * 0.85), mkLine);
      final path = Path()
        ..moveTo(x - 4, size.height * 0.30)
        ..lineTo(x + 4, size.height * 0.30)
        ..lineTo(x, size.height * 0.42)
        ..close();
      canvas.drawPath(path, mkFill);
    }
  }

  @override
  bool shouldRepaint(covariant _RulerPainter old) =>
      old.rangeEnd != rangeEnd ||
      old.spans.length != spans.length ||
      old.pxPerSec != pxPerSec ||
      old.marks.length != marks.length;
}
