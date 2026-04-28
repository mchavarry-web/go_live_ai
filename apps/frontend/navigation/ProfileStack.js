import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { colors } from '../theme';
import ProfileScreen from '../screens/profile/ProfileScreen';
import AvatarCustomizeScreen from '../screens/profile/AvatarCustomizeScreen';
import AvatarBehaviorScreen from '../screens/profile/AvatarBehaviorScreen';
import EditPersonalityScreen from '../screens/profile/EditPersonalityScreen';
import MemoryManagerScreen from '../screens/profile/MemoryManagerScreen';
import DataAccessScreen from '../screens/profile/DataAccessScreen';
import ConversationStatsScreen from '../screens/profile/ConversationStatsScreen';
import TeachAvatarScreen from '../screens/profile/TeachAvatarScreen';

const Stack = createNativeStackNavigator();

const headerOpts = {
  headerStyle: { backgroundColor: colors.surface },
  headerTitleStyle: { color: colors.textPrimary },
  headerTintColor: colors.textPrimary,
  headerShadowVisible: false,
};

export default function ProfileStack() {
  return (
    <Stack.Navigator screenOptions={headerOpts}>
      <Stack.Screen name="ProfileHome" component={ProfileScreen} options={{ title: 'Perfil' }} />
      <Stack.Screen name="AvatarCustomize" component={AvatarCustomizeScreen} options={{ title: 'Apariencia' }} />
      <Stack.Screen name="AvatarBehavior" component={AvatarBehaviorScreen} options={{ title: 'Comportamiento' }} />
      <Stack.Screen name="EditPersonality" component={EditPersonalityScreen} options={{ title: 'Editar personalidad' }} />
      <Stack.Screen name="MemoryManager" component={MemoryManagerScreen} options={{ title: 'Memorias' }} />
      <Stack.Screen name="DataAccess" component={DataAccessScreen} options={{ title: 'Acceso a datos' }} />
      <Stack.Screen name="ConversationStats" component={ConversationStatsScreen} options={{ title: 'Estadísticas' }} />
      <Stack.Screen name="TeachAvatar" component={TeachAvatarScreen} options={{ title: 'Enseñar al avatar' }} />
    </Stack.Navigator>
  );
}
