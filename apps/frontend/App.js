import 'react-native-gesture-handler';
import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import * as Updates from 'expo-updates';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { AuthProvider } from './contexts/AuthContext';
import { AudioRecordingProvider } from './contexts/AudioRecordingContext';
import RootNavigator from './navigation/RootNavigator';

async function applyOtaUpdate() {
  if (__DEV__ || !Updates.isEnabled) return;
  try {
    const result = await Updates.checkForUpdateAsync();
    if (result.isAvailable) {
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync();
    }
  } catch (err) {
    console.warn('[ota] update check failed', err);
  }
}

export default function App() {
  useEffect(() => {
    applyOtaUpdate();
  }, []);

  return (
    <SafeAreaProvider>
      <KeyboardProvider>
        <AuthProvider>
          <AudioRecordingProvider>
            <StatusBar style="light" />
            <RootNavigator />
          </AudioRecordingProvider>
        </AuthProvider>
      </KeyboardProvider>
    </SafeAreaProvider>
  );
}
