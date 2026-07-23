import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:video_player/video_player.dart';
import 'package:chewie/chewie.dart';

// Baixa a fatia da gravação pra um arquivo local e reproduz com chewie
// (arquivo local completo → linha do tempo navegável, seek e velocidade).
class PlaybackPage extends StatefulWidget {
  final String url;
  final String title;
  const PlaybackPage({super.key, required this.url, required this.title});
  @override
  State<PlaybackPage> createState() => _PlaybackPageState();
}

class _PlaybackPageState extends State<PlaybackPage> {
  VideoPlayerController? _video;
  ChewieController? _chewie;
  File? _tempFile;
  String _status = 'preparando...';

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      // 1) baixa a fatia pra um arquivo local
      final dir = await getTemporaryDirectory();
      final file = File(
          '${dir.path}/clip_${DateTime.now().millisecondsSinceEpoch}.mp4');
      _tempFile = file;
      final resp =
          await http.Client().send(http.Request('GET', Uri.parse(widget.url)));
      if (resp.statusCode != 200) {
        if (mounted) setState(() => _status = 'erro (${resp.statusCode})');
        return;
      }
      final sink = file.openWrite();
      int bytes = 0;
      int lastMb = -1;
      await for (final chunk in resp.stream) {
        bytes += chunk.length;
        sink.add(chunk);
        final mb = bytes ~/ 1048576;
        if (mb != lastMb) {
          lastMb = mb;
          if (mounted) setState(() => _status = 'baixando... $mb MB');
        }
      }
      await sink.close();

      // 2) toca o arquivo local
      final v = VideoPlayerController.file(file);
      await v.initialize();
      final c = ChewieController(
        videoPlayerController: v,
        autoPlay: true,
        looping: false,
        allowPlaybackSpeedChanging: true,
        playbackSpeeds: const [0.5, 1.0, 1.5, 2.0, 4.0],
        allowFullScreen: true,
        aspectRatio: v.value.aspectRatio == 0 ? 16 / 9 : v.value.aspectRatio,
        materialProgressColors: ChewieProgressColors(
          playedColor: Colors.indigo,
          handleColor: Colors.indigoAccent,
          bufferedColor: Colors.white30,
          backgroundColor: Colors.white24,
        ),
      );
      if (mounted) {
        setState(() {
          _video = v;
          _chewie = c;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _status = 'erro ao carregar o vídeo');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      backgroundColor: Colors.black,
      body: Center(
        child: _chewie != null
            ? Chewie(controller: _chewie!)
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(_status, style: const TextStyle(color: Colors.white70)),
                ],
              ),
      ),
    );
  }

  @override
  void dispose() {
    _chewie?.dispose();
    _video?.dispose();
    _tempFile?.delete().ignore(); // limpa o arquivo temporário
    super.dispose();
  }
}
