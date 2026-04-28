// 1:1 port of the original tab order in gln-mobile-app:
//   Inicio | Chat | Perfil | Ajustes
//
// The Chat tab opens directly into ChatScreen (which has its own
// ConversationDrawer for switching sessions) — there is no list-then-
// detail flow. ConversationsListScreen is kept as a sibling route in
// case some other surface wants to push to it, but is not the entry
// point of the tab.
import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';

import { colors, borders } from '../theme';
import HomeScreen from '../screens/HomeScreen';
import ChatStack from './ChatStack';
import ProfileStack from './ProfileStack';
import SettingsStack from './SettingsStack';

const Tab = createBottomTabNavigator();

const ICONS = {
  HomeTab:     { active: 'home',                 inactive: 'home-outline' },
  ChatTab:     { active: 'chatbubbles',          inactive: 'chatbubbles-outline' },
  ProfileTab:  { active: 'person',               inactive: 'person-outline' },
  SettingsTab: { active: 'settings-sharp',       inactive: 'settings-outline' },
};

export default function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: borders.width.thin,
          height: 85,
          paddingBottom: 28,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        tabBarIcon: ({ color, size, focused }) => {
          const set = ICONS[route.name];
          const name = focused ? set.active : set.inactive;
          return <Ionicons name={name} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="HomeTab"     component={HomeScreen}    options={{ title: 'Inicio'  }} />
      <Tab.Screen name="ChatTab"     component={ChatStack}     options={{ title: 'Chat'    }} />
      <Tab.Screen name="ProfileTab"  component={ProfileStack}  options={{ title: 'Perfil'  }} />
      <Tab.Screen name="SettingsTab" component={SettingsStack} options={{ title: 'Ajustes' }} />
    </Tab.Navigator>
  );
}
