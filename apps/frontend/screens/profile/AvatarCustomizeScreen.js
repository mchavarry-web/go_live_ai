// 1:1 port of gln-mobile-app/src/screens/profile/AvatarCustomizeScreen.tsx.
// Live AvatarFace preview that mirrors color / eye style / glow intensity.
// Persists via PATCH /api/v1/avatar — appearance jsonb keys are
// `color` / `eyes` / `glow` (the original used flat `primary_color` /
// `eye_style` / `glow_intensity`; we map to/from the nested shape).
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import AvatarFace from '../../components/avatar/AvatarFace';
import { colors, spacing, borders } from '../../theme';
import apiService from '../../services/apiService';
import { useAuth } from '../../contexts/AuthContext';

const COLOR_PRESETS = [
  { label: 'Teal',   value: '#00D4AA' },
  { label: 'Azul',   value: '#00B4D8' },
  { label: 'Morado', value: '#A78BFA' },
  { label: 'Rosa',   value: '#F472B6' },
  { label: 'Dorado', value: '#FFB800' },
  { label: 'Verde',  value: '#34D399' },
  { label: 'Rojo',   value: '#FF4757' },
  { label: 'Blanco', value: '#E8E8ED' },
];

const EYE_STYLES = [
  { label: 'Círculos',  value: 'circle', icon: 'ellipse' },
  { label: 'Cuadrados', value: 'square', icon: 'square' },
  { label: 'Líneas',    value: 'line',   icon: 'remove' },
  { label: 'Puntos',    value: 'dots',   icon: 'ellipsis-horizontal' },
];

const GLOW_OPTIONS = [
  { label: 'Bajo',  value: 'low' },
  { label: 'Medio', value: 'medium' },
  { label: 'Alto',  value: 'high' },
];

function ColorPicker({ selected, onSelect }) {
  return (
    <View style={styles.colorGrid}>
      {COLOR_PRESETS.map((preset) => (
        <TouchableOpacity
          key={preset.value}
          style={[
            styles.colorSwatch,
            { backgroundColor: preset.value },
            selected === preset.value && styles.colorSwatchSelected,
          ]}
          onPress={() => onSelect(preset.value)}
          activeOpacity={0.7}
          accessibilityLabel={`Color ${preset.label}`}
        >
          {selected === preset.value && (
            <Ionicons
              name="checkmark"
              size={18}
              color={preset.value === '#E8E8ED' ? '#0A0A0F' : '#FFFFFF'}
            />
          )}
        </TouchableOpacity>
      ))}
    </View>
  );
}

function OptionSelector({ options, selected, onSelect }) {
  return (
    <View style={styles.optionRow}>
      {options.map((option) => (
        <TouchableOpacity
          key={option.value}
          style={[
            styles.optionButton,
            selected === option.value && styles.optionButtonSelected,
          ]}
          onPress={() => onSelect(option.value)}
          activeOpacity={0.7}
          accessibilityLabel={option.label}
        >
          {option.icon && (
            <Ionicons
              name={option.icon}
              size={18}
              color={selected === option.value ? colors.primary : colors.textTertiary}
              style={styles.optionIcon}
            />
          )}
          <Text
            variant="caption"
            color={selected === option.value ? colors.primary : colors.textSecondary}
          >
            {option.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

export default function AvatarCustomizeScreen() {
  const { refreshUserData } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [primaryColor, setPrimaryColor] = useState('#00D4AA');
  const [eyeStyle, setEyeStyle] = useState('circle');
  const [glowIntensity, setGlowIntensity] = useState('medium');

  const [originalState, setOriginalState] = useState({
    name: '',
    primaryColor: '#00D4AA',
    eyeStyle: 'circle',
    glowIntensity: 'medium',
  });

  const fetchAvatar = useCallback(async () => {
    setLoading(true);
    const { success, data } = await apiService.getAvatar();
    if (success) {
      const avatar = data.avatar || data;
      const appearance = avatar?.appearance || {};
      const state = {
        name: avatar?.name ?? '',
        primaryColor: appearance.color ?? '#00D4AA',
        eyeStyle: appearance.eyes ?? 'circle',
        glowIntensity: typeof appearance.glow === 'string' ? appearance.glow : 'medium',
      };
      setName(state.name);
      setPrimaryColor(state.primaryColor);
      setEyeStyle(state.eyeStyle);
      setGlowIntensity(state.glowIntensity);
      setOriginalState(state);
    } else {
      Alert.alert('Error', 'No se pudo cargar la configuración del avatar.');
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAvatar(); }, [fetchAvatar]);

  const hasChanges =
    name !== originalState.name ||
    primaryColor !== originalState.primaryColor ||
    eyeStyle !== originalState.eyeStyle ||
    glowIntensity !== originalState.glowIntensity;

  const handleSave = async () => {
    if (!hasChanges) return;
    setSaving(true);
    const payload = {};
    if (name !== originalState.name) payload.name = name;
    payload.appearance = {
      color: primaryColor,
      eyes: eyeStyle,
      glow: glowIntensity,
    };
    const { success, error } = await apiService.updateAvatar(payload);
    setSaving(false);
    if (success) {
      setOriginalState({ name, primaryColor, eyeStyle, glowIntensity });
      refreshUserData();
      Alert.alert('Listo', 'Tu avatar ha sido personalizado.');
    } else {
      Alert.alert('Error', error || 'No se pudieron guardar los cambios.');
    }
  };

  if (loading) return <LoadingSpinner fullscreen message="Cargando avatar..." />;

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.previewSection}>
          <View style={styles.previewWrapper}>
            <AvatarFace
              size={120}
              state="idle"
              primaryColor={primaryColor}
              eyeStyle={eyeStyle}
              glowIntensity={glowIntensity}
            />
          </View>
          <Text
            variant="body"
            color={colors.textPrimary}
            align="center"
            style={styles.previewName}
          >
            {name || 'Avatar'}
          </Text>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Nombre del Avatar
          </Text>
          <Input
            value={name}
            onChangeText={setName}
            placeholder="Nombre de tu avatar"
            maxLength={100}
          />
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Color Principal
          </Text>
          <Card variant="glass" padding="md">
            <ColorPicker selected={primaryColor} onSelect={setPrimaryColor} />
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Estilo de Ojos
          </Text>
          <Card variant="glass" padding="md">
            <OptionSelector options={EYE_STYLES} selected={eyeStyle} onSelect={setEyeStyle} />
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Efecto de Brillo
          </Text>
          <Card variant="glass" padding="md">
            <OptionSelector
              options={GLOW_OPTIONS}
              selected={glowIntensity}
              onSelect={setGlowIntensity}
            />
          </Card>
        </View>

        <View style={styles.saveSection}>
          <Button
            title={saving ? 'Guardando...' : 'Guardar Cambios'}
            onPress={handleSave}
            disabled={!hasChanges || saving}
            loading={saving}
            fullWidth
          />
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
  previewSection: {
    alignItems: 'center',
    paddingTop: spacing.xl,
    paddingBottom: spacing.md,
  },
  previewWrapper: {
    width: 140,
    height: 140,
    justifyContent: 'center',
    alignItems: 'center',
  },
  previewName: { marginTop: spacing.sm },
  section: { marginTop: spacing.lg },
  sectionTitle: {
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  colorGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    justifyContent: 'center',
  },
  colorSwatch: {
    width: 44,
    height: 44,
    borderRadius: 22,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  colorSwatchSelected: {
    borderColor: colors.textPrimary,
  },
  optionRow: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  optionButton: {
    flex: 1,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    borderRadius: borders.radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionButtonSelected: {
    borderColor: colors.primary,
    backgroundColor: 'rgba(0, 212, 170, 0.08)',
  },
  optionIcon: { marginBottom: spacing.xxs },
  saveSection: {
    marginTop: spacing.xl,
    paddingHorizontal: spacing.md,
  },
});
