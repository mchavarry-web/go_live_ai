// List of past audio sessions. Tap a row to open the detail screen with
// transcript text. Per-session "Eliminar" lives on the detail screen so
// we don't delete by accident from the list.
import React, { useCallback, useState } from 'react';
import { Alert, FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
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
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function formatDuration(secs) {
  if (!secs) return '0s';
  const s = Math.round(secs);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m}m ${r}s` : `${m}m`;
}

const STATUS_LABELS = {
  recording: 'Grabando',
  finalizing: 'Cerrando',
  processing: 'Procesando',
  ready: 'Listo',
  ready_with_errors: 'Con errores',
  failed: 'Falló',
  cancelled: 'Cancelada',
  abandoned: 'Abandonada',
};

const STATUS_COLOR = (status) => {
  if (status === 'ready') return colors.success;
  if (status === 'ready_with_errors' || status === 'failed') return colors.warning;
  if (status === 'cancelled' || status === 'abandoned') return colors.textTertiary;
  return colors.primary;
};

function SessionRow({ session, onPress }) {
  const dur = session.total_duration_seconds || session.duration_seconds || 0;
  const status = session.status || 'ready';
  return (
    <Pressable onPress={onPress} style={styles.rowPressable}>
      <Card variant="default" padding="md">
        <View style={styles.rowTop}>
          <Text variant="body" color={colors.textPrimary}>
            {formatDate(session.started_at)}
          </Text>
          <View style={[styles.statusPill, { borderColor: STATUS_COLOR(status) }]}>
            <Text variant="caption" color={STATUS_COLOR(status)}>
              {STATUS_LABELS[status] || status}
            </Text>
          </View>
        </View>
        <View style={styles.rowMeta}>
          <View style={styles.metaItem}>
            <Ionicons name="time-outline" size={14} color={colors.textTertiary} />
            <Text variant="caption" color={colors.textTertiary} style={styles.metaText}>
              {formatDuration(dur)}
            </Text>
          </View>
          <View style={styles.metaItem}>
            <Ionicons name="layers-outline" size={14} color={colors.textTertiary} />
            <Text variant="caption" color={colors.textTertiary} style={styles.metaText}>
              {session.chunk_count || 0} segmentos
            </Text>
          </View>
        </View>
        {session.transcript_preview ? (
          <Text
            variant="caption"
            color={colors.textSecondary}
            numberOfLines={2}
            style={styles.preview}
          >
            {session.transcript_preview}
          </Text>
        ) : null}
      </Card>
    </Pressable>
  );
}

export default function AudioHistoryScreen({ navigation }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchSessions = useCallback(async () => {
    const res = await apiService.listAudioSessions();
    setSessions(res.success ? (res.data?.sessions || []) : []);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchSessions();
    }, [fetchSessions]),
  );

  const onRefresh = () => {
    setRefreshing(true);
    fetchSessions();
  };

  const wipeAll = () => {
    Alert.alert(
      'Borrar todo el audio',
      'Vamos a eliminar todas las sesiones, archivos y memorias derivadas. Esta acción no se puede deshacer.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Borrar todo',
          style: 'destructive',
          onPress: async () => {
            const r = await apiService.wipeAllAudio();
            if (r.success) fetchSessions();
            else Alert.alert('Error', r.error || 'No se pudo borrar.');
          },
        },
      ],
    );
  };

  if (loading) return <LoadingSpinner fullscreen />;

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <FlatList
        contentContainerStyle={styles.list}
        data={sessions}
        keyExtractor={(s) => s.id}
        ItemSeparatorComponent={() => <View style={{ height: spacing.xs }} />}
        ListHeaderComponent={
          <View style={styles.header}>
            <Text variant="heading" color={colors.textPrimary}>
              Historial de audio
            </Text>
            <Text variant="caption" color={colors.textSecondary}>
              {sessions.length} sesión{sessions.length === 1 ? '' : 'es'}
            </Text>
          </View>
        }
        ListEmptyComponent={
          <Card variant="default" padding="lg">
            <Text variant="body" color={colors.textSecondary} align="center">
              Todavía no grabaste ninguna sesión. Iniciá una desde la barra de
              entrenamiento.
            </Text>
          </Card>
        }
        ListFooterComponent={
          sessions.length > 0 ? (
            <Pressable onPress={wipeAll} style={styles.wipeRow}>
              <Ionicons name="trash" size={16} color={colors.error} />
              <Text variant="caption" color={colors.error} style={styles.wipeText}>
                Borrar todas las sesiones
              </Text>
            </Pressable>
          ) : null
        }
        renderItem={({ item }) => (
          <SessionRow
            session={item}
            onPress={() => navigation.navigate('AudioSessionDetail', { id: item.id })}
          />
        )}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
          />
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.md, paddingBottom: spacing.xxl },
  header: { marginBottom: spacing.md, gap: spacing.xxs },
  rowPressable: { borderRadius: borders.radius.md },

  rowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statusPill: {
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: borders.radius.full,
    borderWidth: borders.width.thin,
  },
  rowMeta: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.xs,
  },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: {},
  preview: { marginTop: spacing.xs },

  wipeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.lg,
  },
  wipeText: { fontWeight: '600' },
});
