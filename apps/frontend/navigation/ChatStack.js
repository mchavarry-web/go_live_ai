// Chat tab: opens directly into ChatScreen with its own ConversationDrawer
// for switching between sessions, matching gln-mobile-app's flow. The
// ConversationsListScreen is kept as a sibling route in case it is ever
// needed (e.g. an admin shortcut), but it's not the tab entry point.
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import ChatScreen from '../screens/chat/ChatScreen';
import ConversationsListScreen from '../screens/chat/ConversationsListScreen';

const Stack = createNativeStackNavigator();

export default function ChatStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Chat" component={ChatScreen} />
      <Stack.Screen name="ConversationsList" component={ConversationsListScreen} />
    </Stack.Navigator>
  );
}
