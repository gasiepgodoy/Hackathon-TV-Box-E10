import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:http/http.dart' as http;

// Widget de vídeo ao vivo (WHEP/WebRTC), pra embutir na tela unificada.
class LiveView extends StatefulWidget {
  final String whepUrl;
  const LiveView({super.key, required this.whepUrl});
  @override
  State<LiveView> createState() => _LiveViewState();
}

class _LiveViewState extends State<LiveView> {
  final _renderer = RTCVideoRenderer();
  RTCPeerConnection? _pc;
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
      pc.onTrack = (e) {
        if (e.streams.isNotEmpty && mounted) {
          setState(() {
            _renderer.srcObject = e.streams[0];
            _hasVideo = true;
          });
        }
      };
      await pc.addTransceiver(
        kind: RTCRtpMediaType.RTCRtpMediaTypeVideo,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.RecvOnly),
      );
      final offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await _waitIce(pc);
      final local = await pc.getLocalDescription();
      final resp = await http.post(Uri.parse(widget.whepUrl),
          headers: {'Content-Type': 'application/sdp'}, body: local!.sdp);
      if (resp.statusCode == 201 || resp.statusCode == 200) {
        await pc.setRemoteDescription(
            RTCSessionDescription(resp.body, 'answer'));
      }
    } catch (_) {}
  }

  Future<void> _waitIce(RTCPeerConnection pc) async {
    if (pc.iceGatheringState ==
        RTCIceGatheringState.RTCIceGatheringStateComplete) {
      return;
    }
    final c = Completer<void>();
    pc.onIceGatheringState = (s) {
      if (s == RTCIceGatheringState.RTCIceGatheringStateComplete &&
          !c.isCompleted) {
        c.complete();
      }
    };
    final t = Timer(const Duration(seconds: 3), () {
      if (!c.isCompleted) c.complete();
    });
    await c.future;
    t.cancel();
  }

  @override
  Widget build(BuildContext context) {
    return _hasVideo
        ? RTCVideoView(_renderer,
            objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitContain)
        : const Center(
            child: CircularProgressIndicator(color: Colors.white54));
  }

  @override
  void dispose() {
    _pc?.close();
    _renderer.dispose();
    super.dispose();
  }
}
