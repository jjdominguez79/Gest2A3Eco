import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gestinem/features/messaging/presentation/voice_recording.dart';
import 'package:record/record.dart';

void main() {
  test('Android prioriza AAC y nunca ofrece Opus para streaming', () {
    final candidates = voiceStreamEncoderCandidates(
      isWeb: false,
      platform: TargetPlatform.android,
    );
    expect(candidates, [AudioEncoder.aacLc, AudioEncoder.pcm16bits]);
    expect(candidates, isNot(contains(AudioEncoder.opus)));
    expect(candidates, isNot(contains(AudioEncoder.wav)));
  });

  test('Web usa PCM16 compatible con streaming', () {
    expect(
      voiceStreamEncoderCandidates(
        isWeb: true,
        platform: TargetPlatform.android,
      ),
      [AudioEncoder.pcm16bits],
    );
  });

  test('PCM16 se encapsula en un WAV valido', () {
    final wav = pcm16ToWav(
      Uint8List.fromList([1, 2, 3, 4]),
      sampleRate: 24000,
      channels: 1,
    );
    final data = ByteData.sublistView(wav);
    expect(ascii.decode(wav.sublist(0, 4)), 'RIFF');
    expect(ascii.decode(wav.sublist(8, 12)), 'WAVE');
    expect(ascii.decode(wav.sublist(36, 40)), 'data');
    expect(data.getUint32(4, Endian.little), 40);
    expect(data.getUint32(24, Endian.little), 24000);
    expect(data.getUint32(40, Endian.little), 4);
    expect(wav.sublist(44), [1, 2, 3, 4]);
  });
}
