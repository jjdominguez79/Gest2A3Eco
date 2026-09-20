import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

const voiceSampleRate = 24000;
const voiceChannelCount = 1;

/// `record` solo admite AAC-LC y PCM16 al grabar a un stream.
///
/// Opus y WAV pueden estar disponibles para grabacion a fichero, pero no para
/// `startStream`; por eso no deben elegirse a partir de `isEncoderSupported`
/// sin tener en cuenta esta matriz especifica.
List<AudioEncoder> voiceStreamEncoderCandidates({
  required bool isWeb,
  required TargetPlatform platform,
}) {
  if (isWeb || platform == TargetPlatform.linux) {
    return const [AudioEncoder.pcm16bits];
  }
  return const [AudioEncoder.aacLc, AudioEncoder.pcm16bits];
}

String voiceStreamExtension(AudioEncoder encoder) => switch (encoder) {
  AudioEncoder.aacLc => 'aac',
  AudioEncoder.pcm16bits => 'wav',
  _ => throw ArgumentError.value(
    encoder,
    'encoder',
    'Codificador no valido para notas de voz en streaming',
  ),
};

Uint8List finalizeVoiceStream(
  AudioEncoder encoder,
  List<int> bytes, {
  required int sampleRate,
  required int channels,
}) {
  final audio = Uint8List.fromList(bytes);
  if (encoder != AudioEncoder.pcm16bits) return audio;
  return pcm16ToWav(audio, sampleRate: sampleRate, channels: channels);
}

@visibleForTesting
Uint8List pcm16ToWav(
  Uint8List pcm, {
  required int sampleRate,
  required int channels,
}) {
  const bitsPerSample = 16;
  const headerLength = 44;
  final result = Uint8List(headerLength + pcm.length);
  final header = ByteData.sublistView(result);

  void ascii(int offset, String value) {
    for (var index = 0; index < value.length; index++) {
      result[offset + index] = value.codeUnitAt(index);
    }
  }

  ascii(0, 'RIFF');
  header.setUint32(4, 36 + pcm.length, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  header.setUint32(16, 16, Endian.little);
  header.setUint16(20, 1, Endian.little);
  header.setUint16(22, channels, Endian.little);
  header.setUint32(24, sampleRate, Endian.little);
  final blockAlign = channels * bitsPerSample ~/ 8;
  header.setUint32(28, sampleRate * blockAlign, Endian.little);
  header.setUint16(32, blockAlign, Endian.little);
  header.setUint16(34, bitsPerSample, Endian.little);
  ascii(36, 'data');
  header.setUint32(40, pcm.length, Endian.little);
  result.setRange(headerLength, result.length, pcm);
  return result;
}
