// Tester-only modal that surfaces the assistant message's hop-by-hop
// roundtrip telemetry (set on the Rails side via metadata.telemetry).
// Each row shows an absolute timestamp plus the delta from the previous
// hop, so a tester can pinpoint whether the slowdown is in the network,
// the API, or the AI model.
import React from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import Text from '../ui/Text';
import { colors, spacing, borders } from '../../theme';

// Order matters — these are the hops in chronological order. Each step's
// description appears in the modal header next to its timestamp.
const HOPS = [
  { key: 'client_sent_at',     label: 'App → red',          hint: 'Mensaje enviado desde el dispositivo' },
  { key: 'api_received_at',    label: 'Red → API',          hint: 'Rails recibió el POST' },
  { key: 'api_to_ai_sent_at',  label: 'API → IA (envío)',   hint: 'Rails llamó a FastAPI' },
  { key: 'ai_received_at',     label: 'IA recibida',        hint: 'FastAPI recibió la solicitud' },
  { key: 'ai_first_token_at',  label: 'IA · 1er token',     hint: 'Primer token del modelo (TTFT)' },
  { key: 'ai_last_token_at',   label: 'IA · último token',  hint: 'Último token del modelo' },
  { key: 'ai_to_api_done_at',  label: 'IA → API (fin)',     hint: 'FastAPI cerró el stream' },
  { key: 'api_to_app_done_at', label: 'API → App',          hint: 'Rails transmitió por ActionCable' },
];

function parse(ts) {
  if (!ts) return null;
  const t = Date.parse(ts);
  return Number.isFinite(t) ? t : null;
}

function fmtAbs(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString(undefined, { hour12: false }) +
      `.${String(d.getMilliseconds()).padStart(3, '0')}`;
  } catch {
    return ts;
  }
}

function fmtDelta(ms) {
  if (ms === null || ms === undefined) return '';
  if (ms < 0) return `${ms} ms`;
  if (ms < 1000) return `+${ms} ms`;
  return `+${(ms / 1000).toFixed(2)} s`;
}

// Seconds elapsed since the chosen baseline (client_sent_at when present,
// else the earliest known hop). Three-decimal precision so a 30.000 s
// reading on a hop is an obvious timeout marker.
function fmtElapsed(ms) {
  if (ms === null || ms === undefined) return '';
  const sign = ms < 0 ? '-' : '';
  return `${sign}${(Math.abs(ms) / 1000).toFixed(3)} s`;
}

export default function TelemetryModal({ visible, telemetry, onClose }) {
  const data = telemetry || {};
  const status = data.status || 'unknown';
  const error  = data.error || null;

  // Compute the wall-clock total from the earliest known hop to the latest.
  const stamps = HOPS
    .map((h) => parse(data[h.key]))
    .filter((t) => t !== null);
  const total = stamps.length >= 2 ? Math.max(...stamps) - Math.min(...stamps) : null;

  // Baseline for the "elapsed since send" column: prefer client_sent_at
  // (the moment the user tapped Send) so testers can read the modal as
  // "how long the user waited at each hop". If it's missing, fall back
  // to the earliest stamped hop so the column is still useful for
  // partial logs.
  const baseline = parse(data.client_sent_at) ?? (stamps.length > 0 ? Math.min(...stamps) : null);

  // For each hop, the delta is from the immediately previous *known* hop
  // — so a missing intermediate doesn't blank out the next one. Elapsed
  // is from the baseline regardless of intermediate gaps.
  let lastKnown = null;
  const rows = HOPS.map((h) => {
    const t = parse(data[h.key]);
    const delta = t !== null && lastKnown !== null ? t - lastKnown : null;
    const elapsed = t !== null && baseline !== null ? t - baseline : null;
    if (t !== null) lastKnown = t;
    return { ...h, raw: data[h.key], t, delta, elapsed };
  });

  return (
    <Modal
      animationType="fade"
      transparent
      visible={visible}
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation?.()}>
          <View style={styles.header}>
            <Text variant="heading" color={colors.textPrimary}>
              Roundtrip
            </Text>
            <Pressable onPress={onClose} style={styles.closeBtn} accessibilityLabel="Cerrar">
              <Text variant="label" color={colors.textSecondary}>×</Text>
            </Pressable>
          </View>

          <View style={styles.summaryRow}>
            <Text variant="caption" color={colors.textSecondary}>Estado: </Text>
            <Text
              variant="caption"
              color={status === 'ok' ? colors.success : status === 'empty' ? colors.warning : colors.error}
              style={styles.statusValue}
            >
              {status}
            </Text>
            {total !== null ? (
              <Text variant="caption" color={colors.textSecondary} style={styles.totalLabel}>
                · total {fmtDelta(total)}
              </Text>
            ) : null}
          </View>

          {error ? (
            <View style={styles.errorBox}>
              <Text variant="caption" color={colors.error}>{error}</Text>
            </View>
          ) : null}

          <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
            {rows.map((r) => (
              <View key={r.key} style={styles.row}>
                <View style={styles.rowLeft}>
                  <Text variant="caption" color={r.t ? colors.textPrimary : colors.textTertiary} style={styles.rowLabel}>
                    {r.label}
                  </Text>
                  <Text variant="caption" color={colors.textTertiary} style={styles.rowHint}>
                    {r.hint}
                  </Text>
                </View>
                <View style={styles.rowRight}>
                  <Text
                    variant="caption"
                    color={r.t ? colors.textPrimary : colors.textTertiary}
                    style={styles.rowTime}
                  >
                    {fmtAbs(r.raw)}
                  </Text>
                  {r.elapsed !== null ? (
                    <Text variant="caption" color={colors.textSecondary} style={styles.rowElapsed}>
                      {fmtElapsed(r.elapsed)}
                    </Text>
                  ) : null}
                  {r.delta !== null ? (
                    <Text variant="caption" color={colors.primary} style={styles.rowDelta}>
                      {fmtDelta(r.delta)}
                    </Text>
                  ) : null}
                </View>
              </View>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: borders.radius.lg,
    borderTopRightRadius: borders.radius.lg,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
    maxHeight: '80%',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  closeBtn: {
    padding: spacing.xs,
    minWidth: 32,
    alignItems: 'center',
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  statusValue: { fontWeight: '700' },
  totalLabel: { marginLeft: spacing.xs },
  errorBox: {
    padding: spacing.xs,
    borderRadius: borders.radius.sm,
    backgroundColor: 'rgba(255, 71, 87, 0.12)',
    borderWidth: borders.width.thin,
    borderColor: colors.error,
    marginBottom: spacing.sm,
  },
  body: { marginTop: spacing.xs },
  bodyContent: { paddingBottom: spacing.md },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: spacing.xs,
    borderBottomWidth: borders.width.thin,
    borderBottomColor: colors.border,
  },
  rowLeft: { flex: 1, paddingRight: spacing.sm },
  rowLabel: { fontWeight: '600' },
  rowHint: { marginTop: 2 },
  rowRight: { alignItems: 'flex-end' },
  rowTime: { fontVariant: ['tabular-nums'] },
  rowElapsed: { fontVariant: ['tabular-nums'], marginTop: 2 },
  rowDelta: { fontVariant: ['tabular-nums'] },
});
