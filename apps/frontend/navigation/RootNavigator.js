import React from 'react';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { useAuth } from '../contexts/AuthContext';
import { LoadingSpinner } from '../components/ui';
import AuthNavigator from './AuthNavigator';
import OnboardingNavigator from './OnboardingNavigator';
import MainTabs from './MainTabs';
import { colors } from '../theme';

const navTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    background: colors.background,
    card: colors.surface,
    text: colors.textPrimary,
    border: colors.border,
    primary: colors.primary,
    notification: colors.primary,
  },
};

export default function RootNavigator() {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) return <LoadingSpinner fullscreen />;

  const onboardingDone = !!user?.onboarding_completed_at;

  return (
    <NavigationContainer theme={navTheme}>
      {!isAuthenticated ? (
        <AuthNavigator />
      ) : !onboardingDone ? (
        <OnboardingNavigator />
      ) : (
        <MainTabs />
      )}
    </NavigationContainer>
  );
}
