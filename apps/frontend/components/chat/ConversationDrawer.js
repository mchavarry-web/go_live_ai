// 1:1 port of gln-mobile-app/src/components/chat/ConversationDrawer.tsx.
// Slide-in side panel listing recent conversations. Tapping the row picks
// it; the "Nueva conversación" CTA at the top creates a fresh one. The
// overlay (semi-transparent backdrop) closes the drawer when tapped.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Dimensions,
  FlatList,
  Pressable,
  StyleSheet,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import Text from '../ui/Text';
import { colors, spacing, typography } from '../../theme';
import apiService from '../../services/apiService';

const SCREEN_WIDTH = Dimensions.get('window').width;
const DRAWER_WIDTH = Math.min(SCREEN_WIDTH * 0.82, 320);

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

function DrawerItem({ conversation, isActive, onPress }) {
  const timeAgo = formatTimeAgo(conversation.last_active_at || conversation.updated_at);
  const lastMessage =
    conversation.last_message?.content || conversation.last_message_preview || '';

  return (
    <Pressable
      onPress={() => onPress(conversation.id)}
      style={({ pressed }) => [
        styles.item,
        isActive && styles.itemActive,
        pressed && styles.itemPressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={`Conversación: ${conversation.title || 'Sin título'}`}
      accessibilityState={{ selected: isActive }}
    >
      <View style={[styles.itemIcon, isActive && styles.itemIconActive]}>
        <Ionicons
          name="chatbubble"
          size={18}
          color={isActive ? colors.primary : colors.textTertiary}
        />
      </View>
      <View style={styles.itemContent}>
        <Text
          variant="label"
          color={isActive ? colors.primary : colors.textPrimary}
          numberOfLines={1}
          style={styles.itemTitle}
        >
          {conversation.title || 'Nueva conversación'}
        </Text>
        <View style={styles.itemMeta}>
          {lastMessage ? (
            <Text
              variant="caption"
              color={colors.textTertiary}
              numberOfLines={1}
              style={styles.itemPreview}
            >
              {lastMessage}
            </Text>
          ) : null}
          <Text variant="caption" color={colors.textTertiary} style={styles.itemTime}>
            {timeAgo}
          </Text>
        </View>
      </View>
      {isActive && <View style={styles.activeIndicator} />}
    </Pressable>
  );
}

export default function ConversationDrawer({
  isOpen,
  activeConversationId,
  onClose,
  onSelectConversation,
  onNewConversation,
}) {
  const insets = useSafeAreaInsets();
  const translateX = useRef(new Animated.Value(-DRAWER_WIDTH)).current;
  const overlayOpacity = useRef(new Animated.Value(0)).current;
  const [isVisible, setIsVisible] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    const { success, data } = await apiService.listConversations();
    if (success) {
      setConversations(data.conversations || data.data || []);
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    if (isOpen) {
      setIsVisible(true);
      refetch();
      Animated.parallel([
        Animated.spring(translateX, {
          toValue: 0,
          useNativeDriver: true,
          tension: 65,
          friction: 11,
        }),
        Animated.timing(overlayOpacity, {
          toValue: 1,
          duration: 220,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(translateX, {
          toValue: -DRAWER_WIDTH,
          duration: 200,
          useNativeDriver: true,
        }),
        Animated.timing(overlayOpacity, {
          toValue: 0,
          duration: 180,
          useNativeDriver: true,
        }),
      ]).start(() => {
        setIsVisible(false);
      });
    }
  }, [isOpen, translateX, overlayOpacity, refetch]);

  const handleNewConversation = useCallback(async () => {
    try {
      setIsCreating(true);
      const { success, data, error } = await apiService.createConversation();
      if (!success) throw new Error(error || 'fail');
      const conv = data.conversation || data;
      refetch();
      onNewConversation(conv.id);
    } catch {
      Alert.alert('Error', 'No se pudo crear la conversación. Intentá de nuevo.');
    } finally {
      setIsCreating(false);
    }
  }, [refetch, onNewConversation]);

  if (!isVisible) return <View />;

  return (
    <View style={StyleSheet.absoluteFillObject} pointerEvents="box-none">
      <Animated.View
        style={[styles.overlay, { opacity: overlayOpacity }]}
        pointerEvents={isOpen ? 'auto' : 'none'}
      >
        <Pressable
          style={StyleSheet.absoluteFillObject}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Cerrar historial"
        />
      </Animated.View>

      <Animated.View style={[styles.drawer, { transform: [{ translateX }] }]}>
        <View style={[styles.drawerHeader, { paddingTop: insets.top + spacing.md }]}>
          <Text variant="heading" color={colors.textPrimary} style={styles.drawerTitle}>
            Conversaciones
          </Text>
          <Pressable
            onPress={onClose}
            style={styles.closeButton}
            accessibilityRole="button"
            accessibilityLabel="Cerrar"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="close" size={22} color={colors.textSecondary} />
          </Pressable>
        </View>

        <Pressable
          onPress={handleNewConversation}
          disabled={isCreating}
          style={({ pressed }) => [styles.newConvButton, pressed && styles.newConvButtonPressed]}
          accessibilityRole="button"
          accessibilityLabel="Nueva conversación"
        >
          {isCreating ? (
            <ActivityIndicator size="small" color={colors.primary} />
          ) : (
            <Ionicons name="add-circle-outline" size={20} color={colors.primary} />
          )}
          <Text variant="label" color={colors.primary} style={styles.newConvText}>
            {isCreating ? 'Creando...' : 'Nueva conversación'}
          </Text>
        </Pressable>

        <View style={styles.divider} />

        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="small" color={colors.primary} />
          </View>
        ) : conversations.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Ionicons name="chatbubbles-outline" size={32} color={colors.textTertiary} />
            <Text
              variant="body"
              color={colors.textTertiary}
              align="center"
              style={styles.emptyText}
            >
              No hay conversaciones aún
            </Text>
          </View>
        ) : (
          <FlatList
            data={conversations}
            renderItem={({ item }) => (
              <DrawerItem
                conversation={item}
                isActive={item.id === activeConversationId}
                onPress={onSelectConversation}
              />
            )}
            keyExtractor={(item) => String(item.id)}
            contentContainerStyle={styles.listContent}
            showsVerticalScrollIndicator={false}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
          />
        )}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.overlay,
  },
  drawer: {
    position: 'absolute',
    top: 0,
    left: 0,
    bottom: 0,
    width: DRAWER_WIDTH,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 4, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 20,
  },
  drawerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
  },
  drawerTitle: {
    fontSize: typography.sizes.lg,
  },
  closeButton: {
    padding: spacing.xs,
  },
  newConvButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.elevated,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.primary,
    borderStyle: 'dashed',
  },
  newConvButtonPressed: { opacity: 0.7 },
  newConvText: { flex: 1 },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginHorizontal: spacing.md,
    marginBottom: spacing.xs,
  },
  listContent: {
    paddingVertical: spacing.xs,
  },
  separator: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 48 + spacing.md,
    marginRight: spacing.md,
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
  },
  emptyText: { marginTop: spacing.xs },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  itemActive: { backgroundColor: colors.elevated },
  itemPressed: { backgroundColor: colors.elevated, opacity: 0.7 },
  itemIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.card,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  itemIconActive: { backgroundColor: `${colors.primary}22` },
  itemContent: { flex: 1, minWidth: 0 },
  itemTitle: {
    fontSize: typography.sizes.sm,
    marginBottom: 2,
  },
  itemMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  itemPreview: {
    flex: 1,
    fontSize: typography.sizes.xs,
  },
  itemTime: {
    fontSize: typography.sizes.xs,
    flexShrink: 0,
  },
  activeIndicator: {
    width: 3,
    height: 24,
    borderRadius: 2,
    backgroundColor: colors.primary,
    marginLeft: spacing.xs,
  },
});
