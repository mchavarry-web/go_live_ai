// One-shot mic permission UX. Used by VoiceEnrollmentScreen as part of
// the audio-training first-start flow. If the user denies permission we
// surface a Settings-link prompt rather than silently failing.
import React, { useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import Text from '../ui/Text';
import Button from '../ui/Button';
import { colors, spacing, borders } from '../../theme';
import { AudioModule } from 'expo-audio';

export default function PermissionGate({ onGranted, children }) {
  const [denied, setDenied] = useState(false);
  const [granted, setGranted] = useState(false);

  const request = async () => {
    const res = await AudioModule.requestRecordingPermissionsAsync();
    if (res.granted || res.status === 'granted') {
      setGranted(true);
      setDenied(false);
      onGranted?.();
    } else {
      setDenied(true);
    }
  };

  if (granted) return children;

  return (
    <View style={styles.container}>
      <View style={styles.iconWrap}>
        <Ionicons name="mic-outline" size={42} color={colors.primary} />
      </View>
      <Text variant="heading" color={colors.textPrimary} align="center" style={styles.title}>
        Permiso de micrófono
      </Text>
      <Text variant="body" color={colors.textSecondary} align="center" style={styles.copy}>
        Tu avatar aprende de tu voz cuando activás el entrenamiento por audio.
        El micrófono solo se usa cuando vos lo iniciás.
      </Text>
      <Button variant="primary" onPress={request} fullWidth>
        Permitir
      </Button>
      {denied && (
        <Text
          variant="caption"
          color={colors.warning}
          align="center"
          style={styles.deniedHint}
          onPress={() => Linking.openSettings()}
        >
          Si rechazaste el permiso, abre Configuración para habilitarlo.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    padding: spacing.lg,
    alignItems: 'center',
    gap: spacing.sm,
  },
  iconWrap: {
    width: 80, height: 80, borderRadius: 40,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(0, 212, 170, 0.1)',
    borderWidth: borders.width.thin, borderColor: colors.primary,
    marginBottom: spacing.sm,
  },
  title: { marginBottom: spacing.xxs },
  copy: { marginBottom: spacing.md },
  deniedHint: { marginTop: spacing.sm, textDecorationLine: 'underline' },
});
