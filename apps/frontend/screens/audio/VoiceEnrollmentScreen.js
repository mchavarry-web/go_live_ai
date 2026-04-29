// First-run gate before audio training unlocks. Captures two short
// phrase recordings (start phrase + stop phrase). Phase 1 stores them
// alongside their text labels but does NOT use them for fingerprinting —
// see AUDIO_TRAINING_PLAN.md §"Why we defer voice fingerprinting to
// Phase 2".
//
// The user picks the trigger phrase text; the recordings are 3-5 second
// audio clips of them saying each phrase. Both must be captured before
// the feature unlocks (per locked-in decision: not skippable).
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders } from '../../theme';
import { useAudioRecording } from '../../contexts/AudioRecordingContext';

const DEFAULT_START = 'Hola Avatar, vamos a practicar.';
const DEFAULT_STOP  = 'Avatar, terminamos por hoy.';

function PhraseStep({ index, title, hint, value, onChangeText, recording, hasAudio, onRecord, onStop, busy }) {
  return (
    <Card variant="default" padding="md">
      <View style={styles.stepHeader}>
        <View style={styles.stepNum}>
          <Text variant="caption" color={colors.textInverse} style={styles.stepNumText}>
            {index}
          </Text>
        </View>
        <Text variant="label" color={colors.textPrimary}>{title}</Text>
      </View>
      <Text variant="caption" color={colors.textSecondary} style={styles.stepHint}>
        {hint}
      </Text>
      <Input
        value={value}
        onChangeText={onChangeText}
        placeholder="Escribí la frase"
        editable={!busy}
        style={styles.input}
      />
      <View style={styles.recordRow}>
        {recording ? (
          <Pressable
            style={[styles.recordButton, styles.recording]}
            onPress={onStop}
            disabled={busy}
          >
            <Ionicons name="stop" size={18} color={colors.textInverse} />
            <Text variant="caption" color={colors.textInverse} style={styles.recordLabel}>
              Detener
            </Text>
          </Pressable>
        ) : (
          <Pressable
            style={[styles.recordButton, hasAudio && styles.recordButtonRecorded]}
            onPress={onRecord}
            disabled={busy}
          >
            <Ionicons
              name={hasAudio ? 'refresh' : 'mic'}
              size={18}
              color={hasAudio ? colors.primary : colors.textPrimary}
            />
            <Text
              variant="caption"
              color={hasAudio ? colors.primary : colors.textPrimary}
              style={styles.recordLabel}
            >
              {hasAudio ? 'Re-grabar' : 'Grabar frase'}
            </Text>
          </Pressable>
        )}
        {hasAudio && !recording && (
          <View style={styles.checkPill}>
            <Ionicons name="checkmark-circle" size={14} color={colors.success} />
            <Text variant="caption" color={colors.success} style={styles.checkLabel}>
              Listo
            </Text>
          </View>
        )}
      </View>
    </Card>
  );
}

export default function VoiceEnrollmentScreen({ navigation }) {
  const { enroll, enrollment, refreshEnrollment } = useAudioRecording();
  const [startText, setStartText] = useState(DEFAULT_START);
  const [stopText, setStopText] = useState(DEFAULT_STOP);
  const [startUri, setStartUri] = useState(null);
  const [stopUri, setStopUri] = useState(null);
  const [active, setActive] = useState(null); // 'start' | 'stop' | null
  const [submitting, setSubmitting] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const lastUriRef = useRef(null);

  useEffect(() => {
    refreshEnrollment();
  }, [refreshEnrollment]);

  useEffect(() => {
    if (enrollment?.start_phrase_text) setStartText(enrollment.start_phrase_text);
    if (enrollment?.stop_phrase_text) setStopText(enrollment.stop_phrase_text);
  }, [enrollment]);

  const ensurePerm = useCallback(async () => {
    const res = await AudioModule.requestRecordingPermissionsAsync();
    if (!res.granted && res.status !== 'granted') {
      setPermissionDenied(true);
      return false;
    }
    setPermissionDenied(false);
    return true;
  }, []);

  const beginRecording = useCallback(async (which) => {
    if (active) return;
    const ok = await ensurePerm();
    if (!ok) return;
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      setActive(which);
    } catch (err) {
      Alert.alert('Error', `No se pudo iniciar la grabación: ${err.message || err}`);
    }
  }, [active, ensurePerm, recorder]);

  const finishRecording = useCallback(async () => {
    if (!active) return;
    try {
      await recorder.stop();
      const uri = recorder.uri;
      lastUriRef.current = uri;
      if (active === 'start') setStartUri(uri);
      if (active === 'stop') setStopUri(uri);
    } catch (err) {
      Alert.alert('Error', `No se pudo detener la grabación: ${err.message || err}`);
    } finally {
      setActive(null);
      await setAudioModeAsync({ allowsRecording: false });
    }
  }, [active, recorder]);

  const canSubmit =
    !!startUri && !!stopUri &&
    startText.trim().length > 0 &&
    stopText.trim().length > 0 &&
    !active && !submitting;

  const submit = useCallback(async () => {
    setSubmitting(true);
    const res = await enroll({
      startUri, stopUri,
      startText: startText.trim(),
      stopText: stopText.trim(),
    });
    setSubmitting(false);
    if (res.success) {
      Alert.alert(
        'Listo',
        'Tu enrolamiento de voz quedó guardado. Ya podés activar el entrenamiento por audio.',
        [{ text: 'OK', onPress: () => navigation.goBack() }],
      );
    } else {
      Alert.alert('Error', res.error || 'No se pudo guardar el enrolamiento.');
    }
  }, [enroll, startUri, stopUri, startText, stopText, navigation]);

  if (submitting) return <LoadingSpinner fullscreen message="Guardando..." />;

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text variant="heading" color={colors.textPrimary} style={styles.title}>
          Enrolamiento de voz
        </Text>
        <Text variant="body" color={colors.textSecondary} style={styles.intro}>
          Graba dos frases cortas que serán las llaves de tu avatar: una para
          iniciar tus sesiones de entrenamiento y otra para cerrarlas. También
          ayudan a tu avatar a reconocer tu voz cuando estás hablando.
        </Text>

        {permissionDenied && (
          <Card variant="default" padding="sm">
            <Text variant="caption" color={colors.warning} align="center">
              Necesitamos permiso del micrófono. Habilitalo en Configuración.
            </Text>
          </Card>
        )}

        <PhraseStep
          index={1}
          title="Frase de inicio"
          hint="La dices cuando empiezas una sesión."
          value={startText}
          onChangeText={setStartText}
          recording={active === 'start'}
          hasAudio={!!startUri}
          onRecord={() => beginRecording('start')}
          onStop={finishRecording}
          busy={active === 'stop' || submitting}
        />

        <PhraseStep
          index={2}
          title="Frase de cierre"
          hint="La dices cuando terminas la sesión."
          value={stopText}
          onChangeText={setStopText}
          recording={active === 'stop'}
          hasAudio={!!stopUri}
          onRecord={() => beginRecording('stop')}
          onStop={finishRecording}
          busy={active === 'start' || submitting}
        />

        <Button
          variant="primary"
          onPress={submit}
          disabled={!canSubmit}
          fullWidth
          style={styles.submitButton}
        >
          Guardar enrolamiento
        </Button>

        <Text variant="caption" color={colors.textTertiary} align="center" style={styles.note}>
          Tus frases se guardan de forma privada. Podrás borrarlas cuando quieras
          desde Privacidad.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl },
  title: { marginTop: spacing.sm },
  intro: { marginBottom: spacing.xs },

  stepHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  stepNum: {
    width: 22, height: 22, borderRadius: 11,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: colors.primary,
  },
  stepNumText: { fontWeight: '700' },
  stepHint: { marginTop: spacing.xxs, marginBottom: spacing.xs },
  input: { marginBottom: spacing.sm },

  recordRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  recordButton: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.xs,
    paddingHorizontal: spacing.md, paddingVertical: spacing.xs,
    borderRadius: borders.radius.full,
    borderWidth: borders.width.thin, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  recordButtonRecorded: { borderColor: colors.primary },
  recording: { backgroundColor: colors.error, borderColor: colors.error },
  recordLabel: { fontWeight: '600' },

  checkPill: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: spacing.sm, paddingVertical: 2,
    borderRadius: borders.radius.full,
    backgroundColor: 'rgba(0, 212, 170, 0.12)',
  },
  checkLabel: { fontWeight: '600' },

  submitButton: { marginTop: spacing.md },
  note: { marginTop: spacing.xs },
});
