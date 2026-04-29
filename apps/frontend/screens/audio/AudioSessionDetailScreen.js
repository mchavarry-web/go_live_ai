// One audio session — chunk-level transcripts + per-session delete.
//
// Phase 1 ships text-only transcripts (gpt-4o-mini-transcribe doesn't
// return per-utterance segments). If the env is flipped to whisper-1
// we get segments[] back; we render a flat block per chunk either way
// but the segment timestamps are available in the response if a future
// version wants to add scrubbing.
import React, { useCallback, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders } from '../../theme';
import apiService from '../../services/apiService';

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('es-AR', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function formatSeconds(secs) {
  if (!secs) return '0s';
  const s = Math.round(secs);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
}

const CHUNK_STATUS_LABEL = {
  pending: 'Pendiente',
  processing: 'Procesando',
  done: 'Listo',
  failed: 'Falló',
  skipped_quota: 'Omitido (cuota)',
};

const CATEGORY_LABEL = {
  personal_history: 'Historia',
  preference:       'Preferencia',
  relationship:     'Relación',
  goal:             'Meta',
  emotion:          'Emoción',
  health:           'Salud',
};

export default function AudioSessionDetailScreen({ route, navigation }) {
  const { id } = route.params || {};
  const [session, setSession] = useState(null);
  // Insights surfaced from /avatar/insights and filtered to this session's
  // ``source=audio:<id>``. The Rails-side audio job tags each derived
  // insight with that exact source string, so a client-side filter is
  // sufficient and avoids adding a new endpoint just for this view.
  const [sessionInsights, setSessionInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  const fetch = useCallback(async () => {
    const [sessionRes, insightsRes] = await Promise.all([
      apiService.getAudioSession(id),
      apiService.listInsights(),
    ]);
    if (sessionRes.success) setSession(sessionRes.data?.session || sessionRes.data || null);

    const all = insightsRes.success
      ? (insightsRes.data?.insights || insightsRes.data || [])
      : [];
    setSessionInsights(all.filter((i) => i.source === `audio:${id}`));
    setLoading(false);
  }, [id]);

  useFocusEffect(useCallback(() => { fetch(); }, [fetch]));

  const onDelete = () => {
    Alert.alert(
      'Eliminar sesión',
      'Vamos a borrar el audio, las transcripciones y las memorias derivadas de esta sesión.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Eliminar',
          style: 'destructive',
          onPress: async () => {
            setDeleting(true);
            const r = await apiService.deleteAudioSession(id);
            setDeleting(false);
            if (r.success) navigation.goBack();
            else Alert.alert('Error', r.error || 'No se pudo eliminar.');
          },
        },
      ],
    );
  };

  if (loading) return <LoadingSpinner fullscreen />;

  if (!session) {
    return (
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        <Card variant="default" padding="lg">
          <Text variant="body" color={colors.textSecondary} align="center">
            No encontramos esta sesión.
          </Text>
        </Card>
      </SafeAreaView>
    );
  }

  const chunks = session.chunks || [];
  const totalDur =
    session.total_duration_seconds ||
    chunks.reduce((sum, c) => sum + (c.duration_seconds || 0), 0);

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text variant="heading" color={colors.textPrimary}>
          Sesión del {formatDate(session.started_at)}
        </Text>

        <Card variant="default" padding="md">
          <View style={styles.statRow}>
            <View style={styles.statItem}>
              <Text variant="caption" color={colors.textTertiary}>Duración</Text>
              <Text variant="body" color={colors.textPrimary}>{formatSeconds(totalDur)}</Text>
            </View>
            <View style={styles.statItem}>
              <Text variant="caption" color={colors.textTertiary}>Segmentos</Text>
              <Text variant="body" color={colors.textPrimary}>{chunks.length}</Text>
            </View>
            <View style={styles.statItem}>
              <Text variant="caption" color={colors.textTertiary}>Estado</Text>
              <Text variant="body" color={colors.textPrimary}>{session.status || '—'}</Text>
            </View>
          </View>
        </Card>

        <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
          Transcripción
        </Text>

        {chunks.length === 0 ? (
          <Card variant="default" padding="md">
            <Text variant="body" color={colors.textSecondary} align="center">
              Todavía no hay segmentos transcritos.
            </Text>
          </Card>
        ) : (
          chunks.map((c, i) => {
            const status = c.transcription_status || 'pending';
            return (
              <Card key={c.id || i} variant="default" padding="md" style={styles.chunkCard}>
                <View style={styles.chunkHeader}>
                  <Text variant="caption" color={colors.textTertiary}>
                    Segmento {c.sequence_number ?? i + 1} · {formatSeconds(c.duration_seconds)}
                  </Text>
                  <Text
                    variant="caption"
                    color={status === 'done' ? colors.success : colors.textTertiary}
                  >
                    {CHUNK_STATUS_LABEL[status] || status}
                  </Text>
                </View>
                <Text
                  variant="body"
                  color={c.transcript ? colors.textPrimary : colors.textTertiary}
                  style={styles.chunkText}
                >
                  {c.transcript || '— sin texto —'}
                </Text>
              </Card>
            );
          })
        )}

        <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
          Memorias derivadas
        </Text>
        {sessionInsights.length === 0 ? (
          <Card variant="default" padding="md">
            <Text variant="body" color={colors.textSecondary} align="center">
              Esta sesión todavía no produjo memorias. Pueden tardar unos
              segundos en aparecer mientras el avatar procesa la transcripción.
            </Text>
          </Card>
        ) : (
          sessionInsights.map((ins) => (
            <Card key={ins.id} variant="default" padding="md" style={styles.insightCard}>
              <View style={styles.insightHeader}>
                <View style={styles.insightCategoryPill}>
                  <Ionicons name="bulb" size={12} color={colors.primary} />
                  <Text variant="caption" color={colors.primary} style={styles.insightCategoryText}>
                    {CATEGORY_LABEL[ins.category] || ins.category}
                  </Text>
                </View>
                <Text variant="caption" color={colors.textTertiary}>
                  {Math.round((ins.confidence || 0) * 100)}%
                </Text>
              </View>
              <Text variant="body" color={colors.textPrimary} style={styles.insightText}>
                {ins.content}
              </Text>
            </Card>
          ))
        )}

        <Pressable
          onPress={onDelete}
          disabled={deleting}
          style={styles.deleteRow}
        >
          <Ionicons name="trash" size={16} color={colors.error} />
          <Text variant="caption" color={colors.error} style={styles.deleteText}>
            {deleting ? 'Eliminando…' : 'Eliminar esta sesión'}
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl },

  statRow: { flexDirection: 'row', justifyContent: 'space-between' },
  statItem: { gap: spacing.xxs },

  sectionTitle: { marginTop: spacing.xs, marginLeft: spacing.xxs },

  chunkCard: { gap: spacing.xs },
  chunkHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  chunkText: { lineHeight: 22 },

  insightCard: { gap: spacing.xs },
  insightHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  insightCategoryPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: borders.radius.full,
    backgroundColor: 'rgba(0, 212, 170, 0.12)',
  },
  insightCategoryText: { fontWeight: '600' },
  insightText: { lineHeight: 22 },

  deleteRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.lg,
    borderRadius: borders.radius.md,
    borderWidth: borders.width.thin,
    borderColor: colors.error,
    marginTop: spacing.md,
  },
  deleteText: { fontWeight: '600' },
});
