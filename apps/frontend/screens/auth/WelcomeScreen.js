// 1:1 port of gln-mobile-app/src/screens/auth/WelcomeScreen.tsx.
// Brand: "Go Life" with a "GL" logo inside concentric circles, pulsing glow
// ring around it. Auth options: Google, Apple (iOS only), Email. No Facebook
// — that's a *connection* in the original app, not a sign-in method.
import React, { useEffect, useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  Easing,
} from 'react-native-reanimated';
import { colors, spacing, typography } from '../../theme';
import { Text, Button, LoadingSpinner, ErrorMessage } from '../../components/ui';
import { useAuth } from '../../contexts/AuthContext';
import { signInWithGoogle, signInWithApple } from '../../services/socialAuth';

const GLOW_SIZE = 180;
const LOGO_SIZE = 96;

function GlowRing() {
  const pulseScale = useSharedValue(1);
  const pulseOpacity = useSharedValue(0.45);

  useEffect(() => {
    pulseScale.value = withRepeat(
      withSequence(
        withTiming(1.18, { duration: 2400, easing: Easing.inOut(Easing.ease) }),
        withTiming(1,    { duration: 2400, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
    pulseOpacity.value = withRepeat(
      withSequence(
        withTiming(0.7, { duration: 2400, easing: Easing.inOut(Easing.ease) }),
        withTiming(0.3, { duration: 2400, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
  }, [pulseScale, pulseOpacity]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulseScale.value }],
    opacity: pulseOpacity.value,
  }));

  return <Animated.View style={[styles.glowRing, animatedStyle]} />;
}

export default function WelcomeScreen({ navigation }) {
  const { loginWithProvider } = useAuth();
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');

  const isAnyLoading = !!busy;
  const appleAvailable = Platform.OS === 'ios';

  const runProvider = async (providerName, fn) => {
    setError('');
    setBusy(providerName);
    try {
      const { provider, token, webRedirect } = await fn();
      if (webRedirect) {
        setError(`Inicia sesión con ${provider} desde el navegador en ${webRedirect}`);
        return;
      }
      const res = await loginWithProvider(provider, token);
      if (!res.success) setError(res.error || 'No se pudo iniciar sesión');
    } catch (e) {
      setError(e?.message || `Falló el inicio de sesión con ${providerName}`);
    } finally {
      setBusy(null);
    }
  };

  if (isAnyLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <LoadingSpinner fullscreen />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      {/* Top spacer */}
      <View style={styles.topSpacer} />

      {/* Logo + branding */}
      <View style={styles.logoSection}>
        <View style={styles.glowContainer}>
          <GlowRing />
          <View style={styles.logoCircle}>
            <Text style={styles.logoText}>GL</Text>
          </View>
        </View>

        <Text align="center" style={styles.appTitle}>Go Life</Text>
        <Text variant="body" color="textSecondary" align="center" style={styles.subtitle}>
          Tu compañero digital inteligente
        </Text>
      </View>

      {/* Auth buttons */}
      <View style={styles.buttonsSection}>
        {error ? <ErrorMessage message={error} style={styles.error} /> : null}

        <Button
          fullWidth
          size="lg"
          variant="secondary"
          loading={busy === 'google'}
          disabled={isAnyLoading}
          onPress={() => runProvider('google', signInWithGoogle)}
        >
          Continuar con Google
        </Button>

        {appleAvailable ? (
          <Button
            fullWidth
            size="lg"
            variant="ghost"
            loading={busy === 'apple'}
            disabled={isAnyLoading}
            onPress={() => runProvider('apple', signInWithApple)}
          >
            Continuar con Apple
          </Button>
        ) : null}

        <Button
          fullWidth
          size="lg"
          variant="ghost"
          disabled={isAnyLoading}
          onPress={() => navigation.navigate('EmailAuth')}
        >
          Continuar con correo
        </Button>
      </View>

      {/* Footer */}
      <View style={styles.footer}>
        <Text variant="caption" color="textTertiary" align="center" style={styles.footerText}>
          Al continuar, aceptás nuestros{' '}
          <Text variant="caption" color="primary">Términos</Text>
          {' '}y{' '}
          <Text variant="caption" color="primary">Política de Privacidad</Text>
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    paddingHorizontal: spacing.lg,
  },
  topSpacer: { flex: 0.12 },
  logoSection: {
    flex: 0.45,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonsSection: {
    flex: 0.33,
    justifyContent: 'flex-start',
    gap: spacing.sm,
  },
  footer: {
    flex: 0.1,
    justifyContent: 'flex-end',
    paddingBottom: spacing.md,
  },

  glowContainer: {
    width: GLOW_SIZE,
    height: GLOW_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xl,
  },
  glowRing: {
    position: 'absolute',
    width: GLOW_SIZE,
    height: GLOW_SIZE,
    borderRadius: GLOW_SIZE / 2,
    borderWidth: 2,
    borderColor: colors.primary,
    ...Platform.select({
      ios: {
        shadowColor: colors.primary,
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.6,
        shadowRadius: 30,
      },
      android: { elevation: 12 },
    }),
  },

  logoCircle: {
    width: LOGO_SIZE,
    height: LOGO_SIZE,
    borderRadius: LOGO_SIZE / 2,
    backgroundColor: colors.surface,
    borderWidth: 1.5,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoText: {
    fontFamily: typography.fontFamilies.display,
    fontSize: typography.sizes.xxxl,
    // The base Text variant defaults to body lineHeight (24); without an
    // explicit override, the 36px glyph clips at the top of the circle.
    lineHeight: typography.sizes.xxxl,
    fontWeight: typography.weights.extrabold,
    color: colors.primary,
    letterSpacing: 2,
    textAlign: 'center',
    textAlignVertical: 'center',
    includeFontPadding: false,
  },

  appTitle: {
    fontFamily: typography.fontFamilies.display,
    fontSize: typography.sizes.xxxl,
    lineHeight: typography.lineHeights.xxxl,
    fontWeight: typography.weights.extrabold,
    color: colors.textPrimary,
    letterSpacing: 1,
  },
  subtitle: {
    marginTop: spacing.xs,
    letterSpacing: 0.3,
  },

  error: { marginBottom: spacing.xs },
  footerText: { lineHeight: 18 },
});
