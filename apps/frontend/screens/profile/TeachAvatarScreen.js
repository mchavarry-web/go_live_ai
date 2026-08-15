// 1:1 port of gln-mobile-app/src/screens/profile/TeachAvatarScreen.tsx.
// "Teach the avatar" form — text area + category chips + suggestions list
// + history of manual insights.
//
// Backend wiring:
//   POST /api/v1/avatar/teach { message, category? } → AiAgentsClient#teach
//     → FastAPI persists a manual insight against this user.
//   GET  /api/v1/avatar/insights                     → re-fetch the list.
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders, typography } from '../../theme';
import apiService from '../../services/apiService';

const CATEGORIES = [
  { key: 'personal_history', label: 'Historia Personal', icon: 'person',  color: '#00B4D8' },
  { key: 'preference',       label: 'Preferencia',       icon: 'heart',   color: '#F472B6' },
  { key: 'relationship',     label: 'Relación',          icon: 'people',  color: '#A78BFA' },
  { key: 'goal',             label: 'Meta',              icon: 'flag',    color: '#34D399' },
  { key: 'emotion',          label: 'Emoción',           icon: 'happy',   color: '#FFB800' },
  { key: 'health',           label: 'Salud',             icon: 'fitness', color: '#FF4757' },
];

const SUGGESTIONS = [
  { question: '¿Cuál es tu comida favorita?',          category: 'preference' },
  { question: '¿Tienes mascotas?',                     category: 'personal_history' },
  { question: '¿Cuál es tu meta para este año?',       category: 'goal' },
  { question: '¿Qué te hace feliz?',                   category: 'emotion' },
  { question: '¿Cuál es tu pasatiempo favorito?',      category: 'preference' },
  { question: '¿A dónde te gustaría viajar?',          category: 'goal' },
  { question: '¿Cómo prefieres relajarte?',            category: 'preference' },
  { question: '¿Qué tipo de música te gusta?',         category: 'preference' },
  { question: '¿Cuál es tu recuerdo más feliz?',       category: 'emotion' },
  { question: '¿Tienes hermanos?',                     category: 'relationship' },
];

function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
}

function SuggestionCard({ question, category, onPress }) {
  const cat = CATEGORIES.find((c) => c.key === category);
  return (
    <TouchableOpacity
      style={styles.suggestionCard}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Ionicons
        name={cat?.icon || 'bulb'}
        size={18}
        color={cat?.color || colors.primary}
        style={styles.suggestionIcon}
      />
      <Text variant="body" color={colors.textPrimary} style={styles.suggestionText}>
        {question}
      </Text>
      <Ionicons name="arrow-forward" size={16} color={colors.textTertiary} />
    </TouchableOpacity>
  );
}

function ManualInsightItem({ item }) {
  const cat = CATEGORIES.find((c) => c.key === item.category);
  return (
    <View style={styles.manualItem}>
      <View style={[styles.manualDot, { backgroundColor: cat?.color || colors.primary }]} />
      <View style={styles.manualContent}>
        <Text variant="body" color={colors.textPrimary}>{item.content}</Text>
        <Text variant="caption" color={colors.textTertiary}>
          {cat?.label ?? item.category} · {formatDate(item.created_at)}
        </Text>
      </View>
    </View>
  );
}

export default function TeachAvatarScreen() {
  const [content, setContent] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('preference');
  const [saving, setSaving] = useState(false);
  const [manualInsights, setManualInsights] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [activeSuggestion, setActiveSuggestion] = useState(null);

  const fetchManualInsights = useCallback(async () => {
    setLoadingHistory(true);
    const { success, data } = await apiService.listInsights();
    if (success) {
      const all = data.insights || data || [];
      setManualInsights(all.filter((i) => i.source === 'manual'));
    }
    setLoadingHistory(false);
  }, []);

  useEffect(() => { fetchManualInsights(); }, [fetchManualInsights]);

  const handleSubmit = async () => {
    const trimmed = content.trim();
    if (!trimmed) return;
    setSaving(true);
    const { success, error, sessionExpired } = await apiService.teachAvatar(
      trimmed,
      selectedCategory,
    );
    setSaving(false);
    if (success) {
      setContent('');
      setActiveSuggestion(null);
      Alert.alert('Listo', 'Tu avatar aprendió algo nuevo.');
      fetchManualInsights();
    } else if (!sessionExpired) {
      // Surface the server's message (e.g. "No se pudo guardar la
      // enseñanza...") instead of pretending it worked.
      Alert.alert('Error', error || 'No se pudo enseñar al avatar.');
    }
  };

  const handleSuggestionPress = (question, category) => {
    setActiveSuggestion(question);
    setSelectedCategory(category);
    setContent('');
  };

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.headerSection}>
          <Ionicons name="school" size={32} color={colors.primary} />
          <Text variant="subheading" color={colors.textPrimary} style={styles.headerTitle}>
            Enseña a tu avatar
          </Text>
          <Text variant="body" color={colors.textSecondary} align="center">
            Agrega información que quieres que tu avatar recuerde sobre ti
          </Text>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            {activeSuggestion || 'Dile algo a tu avatar'}
          </Text>
          <TextInput
            style={styles.contentInput}
            value={content}
            onChangeText={setContent}
            placeholder={activeSuggestion ? 'Tu respuesta...' : 'Ej: Me encanta cocinar pasta los domingos'}
            placeholderTextColor={colors.textTertiary}
            multiline
            numberOfLines={3}
            maxLength={1000}
            selectionColor={colors.primary}
          />
          <Text variant="caption" color={colors.textTertiary} style={styles.charCount}>
            {content.length}/1000
          </Text>

          <Text variant="label" color={colors.textSecondary} style={styles.categoryTitle}>
            Categoría
          </Text>
          <View style={styles.categoryGrid}>
            {CATEGORIES.map((cat) => (
              <TouchableOpacity
                key={cat.key}
                style={[
                  styles.categoryOption,
                  selectedCategory === cat.key && styles.categoryOptionSelected,
                  selectedCategory === cat.key && { borderColor: cat.color },
                ]}
                onPress={() => setSelectedCategory(cat.key)}
                activeOpacity={0.7}
              >
                <Ionicons
                  name={cat.icon}
                  size={16}
                  color={selectedCategory === cat.key ? cat.color : colors.textTertiary}
                />
                <Text
                  variant="caption"
                  color={selectedCategory === cat.key ? cat.color : colors.textSecondary}
                >
                  {cat.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <Button
            title={saving ? 'Guardando...' : 'Enseñar al Avatar'}
            onPress={handleSubmit}
            disabled={!content.trim() || saving}
            loading={saving}
            fullWidth
          />
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Sugerencias
          </Text>
          <Text variant="caption" color={colors.textTertiary} style={styles.sectionSubtitle}>
            Toca una pregunta para responderla
          </Text>
          {SUGGESTIONS.map((sug, index) => (
            <SuggestionCard
              key={index}
              question={sug.question}
              category={sug.category}
              onPress={() => handleSuggestionPress(sug.question, sug.category)}
            />
          ))}
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Lo que has enseñado ({manualInsights.length})
          </Text>
          {loadingHistory ? (
            <View style={styles.loadingContainer}>
              <LoadingSpinner message="Cargando..." />
            </View>
          ) : manualInsights.length > 0 ? (
            <Card variant="glass" padding="md">
              {manualInsights.map((item, index) => (
                <View key={item.id}>
                  {index > 0 && <View style={styles.divider} />}
                  <ManualInsightItem item={item} />
                </View>
              ))}
            </Card>
          ) : (
            <View style={styles.emptyContainer}>
              <Ionicons name="book-outline" size={32} color={colors.textTertiary} />
              <Text variant="body" color={colors.textTertiary} align="center">
                Aún no le has enseñado nada a tu avatar.
              </Text>
            </View>
          )}
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
  },
  headerSection: {
    alignItems: 'center',
    paddingTop: spacing.xl,
    paddingBottom: spacing.md,
    gap: spacing.xs,
  },
  headerTitle: { marginTop: spacing.xs },
  section: { marginTop: spacing.lg },
  sectionTitle: {
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  sectionSubtitle: {
    marginBottom: spacing.sm,
    marginLeft: spacing.xxs,
  },
  contentInput: {
    backgroundColor: colors.surface,
    borderRadius: borders.radius.md,
    padding: spacing.md,
    fontSize: typography.sizes.md,
    fontFamily: typography.fontFamilies.body,
    color: colors.textPrimary,
    minHeight: 80,
    textAlignVertical: 'top',
    borderWidth: 1,
    borderColor: colors.border,
  },
  charCount: {
    textAlign: 'right',
    marginTop: spacing.xxs,
    marginBottom: spacing.md,
  },
  categoryTitle: { marginBottom: spacing.xs },
  categoryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginBottom: spacing.lg,
  },
  categoryOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.elevated,
  },
  categoryOptionSelected: {
    backgroundColor: 'rgba(0, 212, 170, 0.08)',
  },
  suggestionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.glassBg,
    borderRadius: borders.radius.md,
    padding: spacing.sm,
    marginBottom: spacing.xs,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  suggestionIcon: { marginRight: spacing.sm },
  suggestionText: { flex: 1 },
  manualItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: spacing.xs,
    gap: spacing.sm,
  },
  manualDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginTop: 6,
  },
  manualContent: { flex: 1 },
  divider: {
    height: 1,
    backgroundColor: colors.border,
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
    gap: spacing.sm,
  },
  loadingContainer: {
    paddingVertical: spacing.lg,
  },
});
