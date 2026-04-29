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

const RECORDING_PRESET = RecordingPresets.HIGH_QUALITY;

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
