import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;

// Tela de vídeo ao vivo via WHEP (WebRTC do MediaMTX).
class VideoPage extends StatefulWidget {
  final String whepUrl;
  const VideoPage({super.key, required this.whepUrl});
  @override
  State<VideoPage> createState() => _VideoPageState();
}

class _VideoPageState extends State<VideoPage> {
  final _renderer = RTCVideoRenderer();
  RTCPeerConnection? _pc;
  String _status = 'conectando...';
  bool _hasVideo = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    await _renderer.initialize();
    try {
      final pc = await createPeerConnection({
        'iceServers': [
          {'urls': 'stun:stun.l.google.com:19302'}
        ],
        'sdpSemantics': 'unified-plan',
      });
      _pc = pc;

      pc.onTrack = (event) {
        if (event.streams.isNotEmpty) {
          setState(() {
            _renderer.srcObject = event.streams[0];
            _hasVideo = true;
            _status = 'ao vivo';
          });
        }
      };

      // Só recebemos vídeo (recvonly)
      await pc.addTransceiver(
        kind: RTCRtpMediaType.RTCRtpMediaTypeVideo,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.RecvOnly),
      );

      final offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await _waitIceGathering(pc);

      final local = await pc.getLocalDescription();
      final resp = await http.post(
        Uri.parse(widget.whepUrl),
        headers: {'Content-Type': 'application/sdp'},
        body: local!.sdp,
      );
      if (resp.statusCode != 201 && resp.statusCode != 200) {
        setState(() => _status = 'erro WHEP (${resp.statusCode})');
        return;
      }
      await pc.setRemoteDescription(
          RTCSessionDescription(resp.body, 'answer'));
    } catch (e) {
      if (mounted) setState(() => _status = 'erro: $e');
    }
  }

  // WHEP não faz trickle: junta os candidatos ICE antes de enviar a oferta.
  Future<void> _waitIceGathering(RTCPeerConnection pc) async {
    if (pc.iceGatheringState ==
        RTCIceGatheringState.RTCIceGatheringStateComplete) {
      return;
    }
    final completer = Completer<void>();
    pc.onIceGatheringState = (state) {
      if (state == RTCIceGatheringState.RTCIceGatheringStateComplete &&
          !completer.isCompleted) {
        completer.complete();
      }
    };
    final t = Timer(const Duration(seconds: 3), () {
      if (!completer.isCompleted) completer.complete();
    });
    await completer.future;
    t.cancel();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Câmera ao vivo · $_status')),
      backgroundColor: Colors.black,
      body: Center(
        child: _hasVideo
            ? RTCVideoView(_renderer, objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitContain)
            : Text(_status, style: const TextStyle(color: Colors.white70)),
      ),
    );
  }

  @override
  void dispose() {
    _pc?.close();
    _renderer.dispose();
    super.dispose();
  }
}
