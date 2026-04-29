// 1:1 port of gln-mobile-app/src/screens/profile/MemoryManagerScreen.tsx,
// adapted to our backend:
//   - GET    /api/v1/avatar/insights      → list memories
//   - DELETE /api/v1/avatar/insights/:id  → delete one
//   - DELETE /api/v1/avatar/insights      → delete all
// Editing memories isn't yet exposed by Rails; the inline edit modal is
// kept disabled-on-save (with a toast) until the endpoint lands.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import ErrorMessage from '../../components/ui/ErrorMessage';
import { colors, spacing, borders, typography } from '../../theme';
import apiService from '../../services/apiService';
import { useAuth } from '../../contexts/AuthContext';

const CATEGORIES = [
  { key: 'all',              label: 'Todas' },
  { key: 'personal_history', label: 'Historia',     icon: 'person',  color: '#00B4D8' },
  { key: 'preference',       label: 'Preferencias', icon: 'heart',   color: '#F472B6' },
  { key: 'relationship',     label: 'Relaciones',   icon: 'people',  color: '#A78BFA' },
  { key: 'goal',             label: 'Metas',        icon: 'flag',    color: '#34D399' },
  { key: 'emotion',          label: 'Emociones',    icon: 'happy',   color: '#FFB800' },
  { key: 'health',           label: 'Salud',        icon: 'fitness', color: '#FF4757' },
];

const CATEGORY_MAP = {};
CATEGORIES.forEach((c) => {
  if (c.key !== 'all') {
    CATEGORY_MAP[c.key] = { icon: c.icon, color: c.color, label: c.label };
  }
});

function getCategoryInfo(category) {
  return CATEGORY_MAP[category] || { icon: 'bulb', color: colors.primary, label: category };
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });
}

// Audio insights are tagged ``audio:<session_id>`` by the Rails job, so
// strip the suffix and surface the family name. Other namespaced sources
// (e.g. ``social:twitter``) get the same prefix-aware treatment.
const SOURCE_LABELS = {
  conversation: 'Conversación',
  manual:       'Manual',
  social:       'Red Social',
  audio:        'Audio',
  twitter:      'Twitter/X',
  instagram:    'Instagram',
  facebook:     'Facebook',
  spotify:      'Spotify',
  onboarding:   'Onboarding',
};

function getSourceLabel(source) {
  if (!source) return '—';
  if (SOURCE_LABELS[source]) return SOURCE_LABELS[source];
  const prefix = source.split(':')[0];
  return SOURCE_LABELS[prefix] || source;
}

function CategoryFilter({ selected, onSelect }) {
  // Wrap-row instead of horizontal scroll: only 7 short categories, so a
  // 2-row layout shows everything at once and avoids the right-edge
  // clipping when the row overflows the screen width.
  return (
    <View style={styles.categoryList}>
      {CATEGORIES.map((item) => (
        <TouchableOpacity
          key={item.key}
          style={[styles.categoryChip, selected === item.key && styles.categoryChipSelected]}
          onPress={() => onSelect(item.key)}
          activeOpacity={0.7}
        >
          <Text
            variant="caption"
            color={selected === item.key ? colors.primary : colors.textSecondary}
            numberOfLines={1}
          >
            {item.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

function InsightCard({ item, onDelete }) {
  const cat = getCategoryInfo(item.category);
  return (
    <Card variant="glass" padding="md" style={styles.insightCard}>
      <View style={styles.insightHeader}>
        <View style={[styles.categoryBadge, { backgroundColor: `${cat.color}15` }]}>
          <Ionicons name={cat.icon} size={14} color={cat.color} />
          <Text variant="caption" color={cat.color} style={styles.categoryLabel}>
            {cat.label}
          </Text>
        </View>
        <View style={styles.insightActions}>
          <TouchableOpacity onPress={onDelete} style={styles.actionBtn} activeOpacity={0.7}>
            <Ionicons name="trash-outline" size={16} color={colors.error} />
          </TouchableOpacity>
        </View>
      </View>
      <Text variant="body" color={colors.textPrimary} style={styles.insightContent}>
        {item.content}
      </Text>
      <View style={styles.insightFooter}>
        <View style={styles.confidenceContainer}>
          <View style={styles.confidenceTrack}>
            <View
              style={[styles.confidenceFill, { width: `${(item.confidence ?? 0) * 100}%` }]}
            />
          </View>
          <Text variant="caption" color={colors.textTertiary}>
            {Math.round((item.confidence ?? 0) * 100)}%
          </Text>
        </View>
        <Text variant="caption" color={colors.textTertiary}>
          {getSourceLabel(item.source)} · {formatDate(item.created_at)}
        </Text>
      </View>
    </Card>
  );
}

export default function MemoryManagerScreen() {
  const { user } = useAuth();
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    setError(null);
    const { success, data, error: err } = await apiService.listInsights();
    if (success) {
      setInsights(data.insights || data || []);
    } else {
      setError(err || 'Error al cargar las memorias.');
    }
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => {
    fetchMemories();
  }, [fetchMemories]));

  const filtered = useMemo(() => {
    let list = insights;
    if (selectedCategory !== 'all') {
      list = list.filter((i) => i.category === selectedCategory);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter((i) => (i.content || '').toLowerCase().includes(q));
    }
    return list;
  }, [insights, selectedCategory, searchQuery]);

  const totalInsights = insights.length;
  const knowledgeLevel = user?.avatar?.knowledge_level ?? 1;

  const handleDelete = (item) => {
    Alert.alert(
      'Eliminar memoria',
      `¿Estás seguro de que quieres eliminar esta memoria?\n\n"${(item.content || '').substring(0, 80)}..."`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Eliminar',
          style: 'destructive',
          onPress: async () => {
            const { success } = await apiService.deleteInsight(item.id);
            if (success) {
              setInsights((prev) => prev.filter((i) => i.id !== item.id));
            } else {
              Alert.alert('Error', 'No se pudo eliminar la memoria.');
            }
          },
        },
      ],
    );
  };

  const handleDeleteAll = () => {
    Alert.alert(
      'Eliminar todas las memorias',
      'Esta acción es irreversible. ¿Estás seguro?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Eliminar todo',
          style: 'destructive',
          onPress: async () => {
            const { success } = await apiService.deleteAllInsights();
            if (success) {
              setInsights([]);
              Alert.alert('Listo', 'Todas las memorias han sido eliminadas.');
            } else {
              Alert.alert('Error', 'No se pudieron eliminar las memorias.');
            }
          },
        },
      ],
    );
  };

  if (loading && insights.length === 0) {
    return <LoadingSpinner fullscreen message="Cargando memorias..." />;
  }

  if (error && insights.length === 0) {
    return (
      <SafeAreaView style={styles.centerContainer}>
        <ErrorMessage
          title="Error"
          message={error}
          onRetry={fetchMemories}
          retryLabel="Reintentar"
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <View style={styles.headerBar}>
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text variant="subheading" color={colors.primary}>{totalInsights}</Text>
            <Text variant="caption" color={colors.textTertiary}>memorias</Text>
          </View>
          <View style={styles.statItem}>
            <Text variant="subheading" color={colors.primary}>{knowledgeLevel}</Text>
            <Text variant="caption" color={colors.textTertiary}>nivel</Text>
          </View>
          <TouchableOpacity
            style={styles.deleteAllBtn}
            onPress={handleDeleteAll}
            activeOpacity={0.7}
          >
            <Ionicons name="trash-outline" size={16} color={colors.error} />
            <Text variant="caption" color={colors.error}>Borrar todo</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.searchContainer}>
        <View style={styles.searchBar}>
          <Ionicons name="search" size={18} color={colors.textTertiary} />
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar memorias..."
            placeholderTextColor={colors.textTertiary}
            value={searchQuery}
            onChangeText={setSearchQuery}
            returnKeyType="search"
            selectionColor={colors.primary}
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <Ionicons name="close-circle" size={18} color={colors.textTertiary} />
            </TouchableOpacity>
          )}
        </View>
      </View>

      <CategoryFilter selected={selectedCategory} onSelect={setSelectedCategory} />

      <FlatList
        data={filtered}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <InsightCard item={item} onDelete={() => handleDelete(item)} />
        )}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="bulb-outline" size={48} color={colors.textTertiary} />
            <Text variant="body" color={colors.textTertiary} align="center" style={styles.emptyText}>
              {searchQuery
                ? 'No se encontraron memorias para tu búsqueda.'
                : 'Tu avatar aún no tiene memorias.'}
            </Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centerContainer: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
  },
  headerBar: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statItem: {
    alignItems: 'center',
    marginRight: spacing.lg,
  },
  deleteAllBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginLeft: 'auto',
    paddingVertical: spacing.xxs,
    paddingHorizontal: spacing.sm,
    borderRadius: borders.radius.md,
    borderWidth: 1,
    borderColor: colors.error,
  },
  searchContainer: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xs,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: borders.radius.md,
    paddingHorizontal: spacing.sm,
    height: 44,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  searchInput: {
    flex: 1,
    fontSize: typography.sizes.sm,
    fontFamily: typography.fontFamilies.body,
    color: colors.textPrimary,
    paddingVertical: 0,
  },
  categoryList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    gap: spacing.xs,
  },
  categoryChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.elevated,
    height: 32,
    justifyContent: 'center',
    alignItems: 'center',
  },
  categoryChipSelected: {
    borderColor: colors.primary,
    backgroundColor: 'rgba(0, 212, 170, 0.08)',
  },
  listContent: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xxl,
  },
  insightCard: {
    marginTop: spacing.sm,
  },
  insightHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: borders.radius.sm,
    gap: 4,
  },
  categoryLabel: { marginLeft: 2 },
  insightActions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  actionBtn: { padding: spacing.xxs },
  insightContent: { marginBottom: spacing.xs },
  insightFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  confidenceContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xxs,
  },
  confidenceTrack: {
    width: 40,
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  confidenceFill: {
    height: 4,
    backgroundColor: colors.primary,
    borderRadius: 2,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: spacing.xxl * 2,
    gap: spacing.md,
  },
  emptyText: {
    maxWidth: 240,
  },
});
