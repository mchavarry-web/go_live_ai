// 1:1 port of gln-mobile-app/src/screens/chat/ConversationsListScreen.tsx.
// Empty state shows a "Tu avatar te espera" pitch + primary CTA. Populated
// state shows a list with circular icons + last-message preview + relative
// timestamp, plus a circular floating action button (bottom-right).
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';

import { colors, spacing, typography } from '../../theme';
import Text from '../../components/ui/Text';
import Button from '../../components/ui/Button';
import apiService from '../../services/apiService';

function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);
  if (diffMin < 1) return 'ahora';
  if (diffMin < 60) return `${diffMin}m`;
  if (diffHr < 24) return `${diffHr}h`;
  if (diffDay < 7) return `${diffDay}d`;
  return date.toLocaleDateString('es', { day: 'numeric', month: 'short' });
}

function ConversationItem({ conversation, onPress }) {
  const timeAgo = formatTimeAgo(conversation.last_active_at || conversation.updated_at);
  const lastMessage =
    conversation.last_message?.content || conversation.last_message_preview || '';

  return (
    <Pressable
      onPress={() => onPress(conversation.id)}
      style={({ pressed }) => [
        styles.conversationItem,
        pressed && styles.conversationItemPressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={`Conversación: ${conversation.title || 'Sin título'}`}
    >
      <View style={styles.conversationIcon}>
        <Ionicons name="chatbubble" size={22} color={colors.primary} />
      </View>
      <View style={styles.conversationContent}>
        <View style={styles.conversationHeader}>
          <Text
            variant="label"
            color={colors.textPrimary}
            numberOfLines={1}
            style={styles.conversationTitle}
          >
            {conversation.title || 'Nueva conversación'}
          </Text>
          <Text variant="caption" color={colors.textTertiary}>
            {timeAgo}
          </Text>
        </View>
        {lastMessage ? (
          <Text
            variant="body"
            color={colors.textSecondary}
            numberOfLines={2}
            style={styles.lastMessage}
          >
            {lastMessage}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

function EmptyState({ onNewChat, isCreating }) {
  return (
    <View style={styles.emptyContainer}>
      <View style={styles.emptyIcon}>
        <Ionicons name="sparkles" size={40} color={colors.primary} />
      </View>
      <Text
        variant="heading"
        align="center"
        color={colors.textPrimary}
        style={styles.emptyTitle}
      >
        Tu avatar te espera
      </Text>
      <Text
        variant="body"
        align="center"
        color={colors.textSecondary}
        style={styles.emptySubtitle}
      >
        Inicia una conversación y deja que tu avatar te conozca. Cuanto más
        hablen, mejor te entenderá y más personalizada será cada interacción.
      </Text>
      <Button
        title="Comenzar a conversar"
        onPress={onNewChat}
        loading={isCreating}
        variant="primary"
        size="lg"
        fullWidth
        accessibilityLabel="Iniciar nueva conversación"
      />
    </View>
  );
}

export default function ConversationsListScreen({ navigation }) {
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefetching, setIsRefetching] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  const refetch = useCallback(async () => {
    const { success, data } = await apiService.listConversations();
    if (success) {
      setItems(data.conversations || data.data || []);
    }
    setIsLoading(false);
    setIsRefetching(false);
  }, []);

  useFocusEffect(useCallback(() => {
    refetch();
  }, [refetch]));

  const handleOpenConversation = useCallback(
    (conversationId) => {
      navigation.navigate('Chat', { conversationId });
    },
    [navigation],
  );

  const handleNewConversation = useCallback(async () => {
    try {
      setIsCreating(true);
      const { success, data, error } = await apiService.createConversation();
      if (!success) throw new Error(error || 'fail');
      const conv = data.conversation || data;
      refetch();
      navigation.navigate('Chat', { conversationId: conv.id });
    } catch {
      Alert.alert('Error', 'No se pudo crear la conversación. Intentá de nuevo.');
    } finally {
      setIsCreating(false);
    }
  }, [navigation, refetch]);

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.container}>
        <EmptyState onNewChat={handleNewConversation} isCreating={isCreating} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={items}
        renderItem={({ item }) => (
          <ConversationItem conversation={item} onPress={handleOpenConversation} />
        )}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={() => {
              setIsRefetching(true);
              refetch();
            }}
            tintColor={colors.primary}
          />
        }
        ItemSeparatorComponent={() => <View style={styles.separator} />}
      />

      <Pressable
        onPress={handleNewConversation}
        disabled={isCreating}
        style={({ pressed }) => [styles.fab, pressed && styles.fabPressed]}
        accessibilityRole="button"
        accessibilityLabel="Nueva conversación"
      >
        {isCreating ? (
          <ActivityIndicator size="small" color={colors.textInverse} />
        ) : (
          <Ionicons name="add" size={28} color={colors.textInverse} />
        )}
      </Pressable>
    </View>
  );
}

const FAB_SIZE = 56;

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centerContainer: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    paddingVertical: spacing.sm,
  },
  conversationItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  conversationItemPressed: {
    backgroundColor: colors.surface,
  },
  conversationIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.elevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  conversationContent: {
    flex: 1,
  },
  conversationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  conversationTitle: {
    flex: 1,
    marginRight: spacing.sm,
  },
  lastMessage: {
    fontSize: typography.sizes.sm,
    lineHeight: 18,
  },
  separator: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 48 + spacing.lg + spacing.md,
    marginRight: spacing.lg,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    gap: spacing.md,
  },
  emptyIcon: {
    alignSelf: 'center',
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: colors.elevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  emptyTitle: {
    fontSize: typography.sizes.xxl,
  },
  emptySubtitle: {
    lineHeight: 22,
    marginBottom: spacing.sm,
  },
  fab: {
    position: 'absolute',
    bottom: spacing.lg,
    right: spacing.lg,
    width: FAB_SIZE,
    height: FAB_SIZE,
    borderRadius: FAB_SIZE / 2,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 6,
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  fabPressed: {
    opacity: 0.8,
    transform: [{ scale: 0.95 }],
  },
});
