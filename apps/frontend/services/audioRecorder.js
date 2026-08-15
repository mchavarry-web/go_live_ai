// Thin wrapper around expo-audio's AudioRecorder. Handles permission,
// session-mode setup, and chunk rotation: stop the current file, hand its
// URI to the caller, then immediately start a new file.
//
// Recording options match the AAC m4a profile expected by Rails' Shrine
// uploader (audio/mp4 + audio/x-m4a in the validation_helpers allow-list).
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';

// Explicit AAC/m4a mono profile (DEV-97). We base it on HIGH_QUALITY but
// pin what transcription cares about instead of trusting preset defaults:
//   - Android: outputFormat/audioEncoder pinned to mpeg4/aac — some OEM
//     builds fall back to 3gp/amr when the encoder isn't explicit, which
//     gpt-4o-mini-transcribe handles poorly (→ empty transcripts).
//   - mono, 44.1kHz (≥16kHz needed by speech models), 96kbps — smaller
//     uploads than the stereo 128kbps preset with no accuracy loss.
const BASE_PRESET = RecordingPresets.HIGH_QUALITY;
const RECORDING_PRESET = {
  ...BASE_PRESET,
  numberOfChannels: 1,
  sampleRate: 44100,
  bitRate: 96000,
  android: {
    ...(BASE_PRESET.android || {}),
    outputFormat: 'mpeg4',
    audioEncoder: 'aac',
    sampleRate: 44100,
  },
  ios: {
    ...(BASE_PRESET.ios || {}),
    sampleRate: 44100,
    numberOfChannels: 1,
  },
};

// Clips shorter than this are rejected before upload — sub-second files
// are almost always a stray tap and transcribe to "" (DEV-97).
export const MIN_RECORDING_SECONDS = 1;

export async function ensurePermission() {
  const status = await AudioModule.requestRecordingPermissionsAsync();
  return status.granted === true || status.status === 'granted';
}

// Set the audio session into recording mode. Phase 1 keeps it foreground-only;
// Phase 2 will flip ``allowsBackgroundRecording`` once we ship the iOS audio
// background entitlement and the Android foreground service.
export async function configureRecordingSession() {
  await setAudioModeAsync({
    allowsRecording: true,
    playsInSilentMode: true,
    shouldPlayInBackground: false,
  });
}

export async function configureIdleSession() {
  await setAudioModeAsync({
    allowsRecording: false,
    playsInSilentMode: false,
    shouldPlayInBackground: false,
  });
}

// Re-export for hooks that need to drive the recorder imperatively.
export { useAudioRecorder, RECORDING_PRESET };
