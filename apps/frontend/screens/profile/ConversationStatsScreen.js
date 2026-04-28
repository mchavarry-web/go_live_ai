// 1:1 port of gln-mobile-app/src/screens/profile/ConversationStatsScreen.tsx,
// adapted to the data we have: derived from /chat/conversations + /avatar
// + /avatar/insights instead of a single profile endpoint.
//
// Sections:
//   - Stat grid (knowledge level, conversations, total messages, days)
//   - Insights por categoría (count by category w/ mini-bar)
//   - Próximo nivel (gamified progress to next "knowledge tier")
import React, { useCallback, useEffect, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders } from '../../theme';
import { useAuth } from '../../contexts/AuthContext';
import apiService from '../../services/apiService';

const CATEGORY_LABELS = {
  personal_history: { label: 'Historia Personal', color: '#00B4D8', icon: 'person'  },
  preference:       { label: 'Preferencias',      color: '#F472B6', icon: 'heart'   },
  relationship:     { label: 'Relaciones',        color: '#A78BFA', icon: 'people'  },
  goal:             { label: 'Metas',             color: '#34D399', icon: 'flag'    },
  emotion:          { label: 'Emociones',         color: '#FFB800', icon: 'happy'   },
  health:           { label: 'Salud',             color: '#FF4757', icon: 'fitness' },
};

function getKnowledgeLevelLabel(level) {
  if (level <= 2) return 'Principiante';
  if (level <= 4) return 'Aprendiz';
  if (level <= 6) return 'Intermedio';
  if (level <= 8) return 'Avanzado';
  return 'Experto';
}

function getNextLevel(insightsCount) {
  if (insightsCount <= 2)  return { current: insightsCount, target: 3,  label: 'Aprendiz' };
  if (insightsCount <= 5)  return { current: insightsCount, target: 6,  label: 'Intermedio' };
  if (insightsCount <= 10) return { current: insightsCount, target: 11, label: 'Avanzado' };
  if (insightsCount <= 20) return { current: insightsCount, target: 21, label: 'Experto' };
  return { current: insightsCount, target: insightsCount, label: 'Máximo' };
}

function StatCard({ icon, label, value, color = colors.primary }) {
  return (
    <View style={styles.statCard}>
      <View style={[styles.statIconContainer, { backgroundColor: `${color}15` }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <Text variant="subheading" color={colors.textPrimary} style={styles.statValue}>
        {value}
      </Text>
      <Text variant="caption" color={colors.textTertiary}>
        {label}
      </Text>
    </View>
  );
}

function CategoryRow({ category, count, total }) {
  const cfg = CATEGORY_LABELS[category];
  if (!cfg) return null;
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <View style={styles.categoryRow}>
      <View style={[styles.categoryIconBg, { backgroundColor: `${cfg.color}20` }]}>
        <Ionicons name={cfg.icon} size={16} color={cfg.color} />
      </View>
      <View style={styles.categoryBody}>
        <Text variant="body" color={colors.textPrimary}>{cfg.label}</Text>
        <View style={styles.categoryBarTrack}>
          <View style={[styles.categoryBarFill, { width: `${pct}%`, backgroundColor: cfg.color }]} />
        </View>
      </View>
      <Text variant="caption" color={colors.textTertiary} style={styles.categoryCount}>
        {count}
      </Text>
    </View>
  );
}

export default function ConversationStatsScreen() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [insights, setInsights] = useState([]);
  const [conversationCount, setConversationCount] = useState(0);
  const [messageCount, setMessageCount] = useState(0);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    const [insightsRes, convRes] = await Promise.all([
      apiService.listInsights(),
      apiService.listConversations(),
    ]);
    if (insightsRes.success) {
      setInsights(insightsRes.data?.insights || insightsRes.data || []);
    }
    if (convRes.success) {
      const convs = convRes.data?.conversations || convRes.data || [];
      setConversationCount(convs.length);
      setMessageCount(convs.reduce((a, c) => a + (c.messages_count || 0), 0));
    }
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { fetchStats(); }, [fetchStats]));

  if (loading) return <LoadingSpinner fullscreen message="Cargando estadísticas..." />;

  const knowledgeLevel = user?.avatar?.knowledge_level ?? 1;
  const memberSinceDays = user?.created_at
    ? Math.max(1, Math.floor((Date.now() - new Date(user.created_at).getTime()) / 86400000))
    : 0;

  const insightsByCategory = {};
  insights.forEach((i) => {
    const c = i.category || 'preference';
    insightsByCategory[c] = (insightsByCategory[c] || 0) + 1;
  });
  const totalInsights = insights.length;
  const nextLevel = getNextLevel(totalInsights);
  const nextProgress =
    nextLevel.target > 0 ? Math.min(1, nextLevel.current / nextLevel.target) : 1;

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Stat grid */}
        <View style={styles.statsGrid}>
          <StatCard
            icon="flash"
            label={getKnowledgeLevelLabel(knowledgeLevel)}
            value={`${knowledgeLevel}/10`}
            color="#FFB800"
          />
          <StatCard
            icon="chatbubbles"
            label="Conversaciones"
            value={String(conversationCount)}
            color="#00D4AA"
          />
          <StatCard
            icon="chatbox-ellipses"
            label="Mensajes"
            value={String(messageCount)}
            color="#A78BFA"
          />
          <StatCard
            icon="calendar"
            label="Días con tu avatar"
            value={String(memberSinceDays)}
            color="#F472B6"
          />
        </View>

        {/* Insights por categoría */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Insights por categoría ({totalInsights})
          </Text>
          <Card variant="glass" padding="md">
            {Object.keys(insightsByCategory).length === 0 ? (
              <Text variant="body" color={colors.textTertiary}>
                Tu avatar aún no tiene insights.
              </Text>
            ) : (
              Object.entries(insightsByCategory).map(([category, count], i) => (
                <View key={category}>
                  {i > 0 && <View style={styles.divider} />}
                  <CategoryRow
                    category={category}
                    count={count}
                    total={totalInsights}
                  />
                </View>
              ))
            )}
          </Card>
        </View>

        {/* Próximo nivel */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Próximo nivel
          </Text>
          <Card variant="glass" padding="md">
            <View style={styles.nextHeader}>
              <Ionicons name="star" size={18} color={colors.primary} />
              <Text variant="body" color={colors.textPrimary} style={styles.nextLabel}>
                {nextLevel.label}
              </Text>
              <Text variant="caption" color={colors.textTertiary} style={styles.nextCount}>
                {nextLevel.current} / {nextLevel.target}
              </Text>
            </View>
            <View style={styles.nextBarTrack}>
              <View style={[styles.nextBarFill, { width: `${nextProgress * 100}%` }]} />
            </View>
            <Text variant="caption" color={colors.textTertiary} style={styles.nextHint}>
              Cuanto más converses con tu avatar, más rápido sube de nivel.
            </Text>
          </Card>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollView: { flex: 1 },
  scrollContent: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xxl,
    paddingTop: spacing.lg,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  statCard: {
    flexBasis: '48%',
    flexGrow: 1,
    backgroundColor: colors.glassBg,
    borderRadius: borders.radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    alignItems: 'flex-start',
    gap: spacing.xxs,
  },
  statIconContainer: {
    width: 36,
    height: 36,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  statValue: {},
  section: { marginTop: spacing.lg },
  sectionTitle: {
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.xs,
  },
  categoryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  categoryIconBg: {
    width: 32,
    height: 32,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  categoryBody: { flex: 1 },
  categoryBarTrack: {
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: 'hidden',
    marginTop: 4,
  },
  categoryBarFill: {
    height: 4,
    borderRadius: 2,
  },
  categoryCount: {
    minWidth: 24,
    textAlign: 'right',
  },
  nextHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  nextLabel: { flex: 1 },
  nextCount: {},
  nextBarTrack: {
    height: 8,
    backgroundColor: colors.border,
    borderRadius: 4,
    overflow: 'hidden',
    marginTop: spacing.sm,
  },
  nextBarFill: {
    height: 8,
    backgroundColor: colors.primary,
    borderRadius: 4,
  },
  nextHint: {
    marginTop: spacing.xs,
  },
});
