import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { colors } from '../theme';
import SettingsScreen from '../screens/settings/SettingsScreen';
import PrivacyScreen from '../screens/settings/PrivacyScreen';

const Stack = createNativeStackNavigator();

const headerOpts = {
  headerStyle: { backgroundColor: colors.surface },
  headerTitleStyle: { color: colors.textPrimary },
  headerTintColor: colors.textPrimary,
  headerShadowVisible: false,
};

export default function SettingsStack() {
  return (
    <Stack.Navigator screenOptions={headerOpts}>
      <Stack.Screen name="SettingsHome" component={SettingsScreen} options={{ title: 'Ajustes' }} />
      <Stack.Screen name="Privacy" component={PrivacyScreen} options={{ title: 'Privacidad' }} />
    </Stack.Navigator>
  );
}
