// 1:1 port of gln-mobile-app/src/screens/auth/EmailAuthScreen.tsx.
// Pill-toggle (Ingresar / Registrarse) at the top, single "Nombre" field on
// register, Argentine voseo throughout, 6-char password minimum.
import React, { useCallback, useRef, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, spacing, borders, typography } from '../../theme';
import { Text, Button, Input } from '../../components/ui';
import { useAuth } from '../../contexts/AuthContext';

function validate(mode, displayName, email, password) {
  const errors = {};

  if (mode === 'register') {
    if (!displayName.trim()) {
      errors.displayName = 'El nombre es obligatorio.';
    } else if (displayName.trim().length < 2) {
      errors.displayName = 'El nombre debe tener al menos 2 caracteres.';
    }
  }

  if (!email.trim()) {
    errors.email = 'El correo es obligatorio.';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    errors.email = 'Ingresa un correo válido.';
  }

  if (!password) {
    errors.password = 'La contraseña es obligatoria.';
  } else if (mode === 'register' && password.length < 6) {
    errors.password = 'La contraseña debe tener al menos 6 caracteres.';
  }

  return errors;
}

export default function EmailAuthScreen({ navigation }) {
  const { login, register } = useAuth();

  const [mode, setMode] = useState('login');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);

  const emailRef = useRef(null);
  const passwordRef = useRef(null);

  const switchMode = useCallback((next) => {
    setMode(next);
    setErrors({});
  }, []);

  const handleSubmit = useCallback(async () => {
    const validationErrors = validate(mode, displayName, email, password);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }
    setErrors({});

    setIsLoading(true);
    let result;
    if (mode === 'login') {
      result = await login(email.trim(), password);
    } else {
      // Backend expects first_name + last_name; split the single name field on
      // the first space (the original app stored it as a single display_name).
      const trimmed = displayName.trim();
      const idx = trimmed.indexOf(' ');
      const firstName = idx >= 0 ? trimmed.slice(0, idx) : trimmed;
      const lastName  = idx >= 0 ? trimmed.slice(idx + 1) : '';
      result = await register({
        email: email.trim(),
        password,
        firstName,
        lastName,
      });
    }
    setIsLoading(false);

    if (!result?.success) {
      Alert.alert(
        mode === 'login' ? 'Error al ingresar' : 'Error al registrarse',
        result?.error || 'Ocurrió un error. Intentá de nuevo.'
      );
    }
  }, [mode, displayName, email, password, login, register]);

  const isLoginMode = mode === 'login';

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 24}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Back button */}
          <Pressable
            onPress={() => navigation.goBack()}
            style={styles.backButton}
            hitSlop={12}
            accessibilityLabel="Volver"
          >
            <Text variant="body" color="primary">← Volver</Text>
          </Pressable>

          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.title}>
              {isLoginMode ? 'Bienvenido' : 'Crear cuenta'}
            </Text>
            <Text variant="body" color="textSecondary" style={styles.subtitle}>
              {isLoginMode
                ? 'Ingresa con tu correo y contraseña'
                : 'Completa tus datos para registrarte'}
            </Text>
          </View>

          {/* Pill toggle */}
          <View style={styles.toggleContainer}>
            <Pressable
              style={[styles.toggleTab, isLoginMode && styles.toggleTabActive]}
              onPress={() => switchMode('login')}
              accessibilityRole="tab"
              accessibilityState={{ selected: isLoginMode }}
            >
              <Text
                variant="label"
                color={isLoginMode ? 'primary' : 'textTertiary'}
                style={styles.toggleLabel}
              >
                Ingresar
              </Text>
            </Pressable>
            <Pressable
              style={[styles.toggleTab, !isLoginMode && styles.toggleTabActive]}
              onPress={() => switchMode('register')}
              accessibilityRole="tab"
              accessibilityState={{ selected: !isLoginMode }}
            >
              <Text
                variant="label"
                color={!isLoginMode ? 'primary' : 'textTertiary'}
                style={styles.toggleLabel}
              >
                Registrarse
              </Text>
            </Pressable>
          </View>

          {/* Form */}
          <View style={styles.form}>
            {!isLoginMode && (
              <Input
                label="Nombre"
                placeholder="¿Cómo te llamas?"
                value={displayName}
                onChangeText={setDisplayName}
                error={errors.displayName}
                autoCapitalize="words"
                autoComplete="name"
                returnKeyType="next"
                onSubmitEditing={() => emailRef.current?.focus()}
                editable={!isLoading}
              />
            )}

            <Input
              ref={emailRef}
              label="Correo electrónico"
              placeholder="tu@correo.com"
              value={email}
              onChangeText={setEmail}
              error={errors.email}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              editable={!isLoading}
            />

            <Input
              ref={passwordRef}
              label="Contraseña"
              placeholder={isLoginMode ? 'Tu contraseña' : 'Mínimo 6 caracteres'}
              value={password}
              onChangeText={setPassword}
              error={errors.password}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="password"
              textContentType="password"
              passwordRules=""
              returnKeyType="done"
              onSubmitEditing={handleSubmit}
              editable={!isLoading}
            />

            <Button
              fullWidth
              size="lg"
              variant="primary"
              loading={isLoading}
              disabled={isLoading}
              onPress={handleSubmit}
            >
              {isLoginMode ? 'Ingresar' : 'Crear cuenta'}
            </Button>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xl,
  },

  backButton: {
    marginTop: spacing.md,
    alignSelf: 'flex-start',
  },

  header: {
    marginTop: spacing.xl,
    marginBottom: spacing.lg,
  },
  title: {
    fontFamily: typography.fontFamilies.display,
    fontSize: typography.sizes.xxl,
    lineHeight: typography.lineHeights.xxl,
    fontWeight: typography.weights.extrabold,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  subtitle: { lineHeight: 22 },

  toggleContainer: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: borders.radius.md,
    padding: 4,
    marginBottom: spacing.lg,
  },
  toggleTab: {
    flex: 1,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    borderRadius: borders.radius.sm,
  },
  toggleTabActive: {
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  toggleLabel: {
    fontSize: typography.sizes.sm,
    fontWeight: typography.weights.semibold,
  },

  form: { gap: spacing.md },
});
