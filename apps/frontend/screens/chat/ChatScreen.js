// 1:1 port of gln-mobile-app/src/screens/chat/ChatScreen.tsx, adapted to
// our Rails-backed transport: REST POST + ActionCable subscription instead
// of the old SSE flow. The original carried health-data + a proactive
// greeting hook on first load — we keep those concepts but route through
// the apiService that's already wired to Rails.
//
// Visual parity points:
//   - Custom AvatarHeader (no native nav bar) with conversations menu
//     button on the left. State of the avatar (idle/thinking/talking)
//     mirrors the streaming state.
//   - WelcomeMessage when the conversation is empty.
//   - TypingIndicator while the avatar is "thinking" (no tokens yet).
//   - Streaming bubble with a thin primary cursor while tokens arrive.
//   - ErrorRetry bubble inline at the end on send failure.
//   - ConversationDrawer slides in from the left.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { colors, spacing, typography } from '../../theme';
import Text from '../../components/ui/Text';
import AvatarHeader from '../../components/chat/AvatarHeader';
import MessageBubble from '../../components/chat/MessageBubble';
import MarkdownMessage from '../../components/chat/MarkdownMessage';
import ChatInput from '../../components/chat/ChatInput';
import TypingIndicator from '../../components/chat/TypingIndicator';
import ConversationDrawer from '../../components/chat/ConversationDrawer';
import apiService from '../../services/apiService';
import { ChatChannel } from '../../services/chatChannel';
import { useAuth } from '../../contexts/AuthContext';

function WelcomeMessage({ avatarName }) {
  return (
    <View style={styles.welcomeContainer}>
      <View style={styles.welcomeIcon}>
        <Ionicons name="sparkles" size={32} color={colors.primary} />
      </View>
      <Text
        variant="heading"
        align="center"
        color={colors.textPrimary}
        style={styles.welcomeTitle}
      >
        ¡Hablemos!
      </Text>
      <Text
        variant="body"
        align="center"
        color={colors.textSecondary}
        style={styles.welcomeSubtitle}
      >
        Soy {avatarName}, tu avatar personal. Puedo ayudarte a reflexionar,
        explorar ideas o simplemente conversar. ¿Qué tienes en mente?
      </Text>
    </View>
  );
}

function ErrorRetry({ message, onRetry }) {
  return (
    <View style={styles.errorContainer}>
      <View style={styles.errorBubble}>
        <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
        <Text variant="body" color={colors.error} style={styles.errorText}>
          {message}
        </Text>
        <Pressable
          onPress={onRetry}
          style={styles.retryButton}
          accessibilityRole="button"
          accessibilityLabel="Reintentar"
        >
          <Ionicons name="refresh" size={16} color={colors.primary} />
          <Text variant="caption" color={colors.primary}>
            Reintentar
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function ChatScreen({ route, navigation }) {
  const { user } = useAuth();
  const [conversationId, setConversationId] = useState(route.params?.conversationId || null);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');
  const [lastFailedMessage, setLastFailedMessage] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const channelRef = useRef(null);
  const listRef = useRef(null);
  // Tracked as a ref (not state) so flipping it doesn't re-run the bootstrap
  // effect — that would cancel the in-flight listConversations / create call
  // via the cleanup function and silently leave `conversationId` null.
  const creatingConvRef = useRef(false);

  const avatarName = user?.avatar?.name || 'tu avatar';

  // If we landed without a conversationId (typical when the user just taps
  // the Chat tab), reuse the most-recent conversation when one exists, and
  // only create a new one as a fallback. This mirrors gln-mobile-app's
  // useInactivitySession behaviour without the absence-time heuristic.
  useEffect(() => {
    if (conversationId || creatingConvRef.current) return undefined;
    let cancelled = false;
    creatingConvRef.current = true;
    (async () => {
      const list = await apiService.listConversations();
      if (cancelled) { creatingConvRef.current = false; return; }
      const items = list.success ? (list.data?.conversations || list.data || []) : [];
      if (items.length > 0) {
        // The list is sorted by last_active_at DESC server-side
        setConversationId(items[0].id);
        creatingConvRef.current = false;
        return;
      }
      const { success, data } = await apiService.createConversation();
      if (cancelled) { creatingConvRef.current = false; return; }
      if (success) {
        const conv = data.conversation || data;
        setConversationId(conv.id);
      } else {
        setError('No se pudo iniciar la conversación.');
      }
      creatingConvRef.current = false;
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // Keep conversationId in sync with route params
  useEffect(() => {
    if (route.params?.conversationId && route.params.conversationId !== conversationId) {
      setConversationId(route.params.conversationId);
      setMessages([]);
      setStreamBuffer('');
      setStreaming(false);
    }
  }, [route.params?.conversationId, conversationId]);

  // History fetch — runs reliably whenever conversationId changes. We use a
  // plain useEffect rather than useFocusEffect because the screen unmounts
  // when you switch tabs in a stack navigator, and useFocusEffect's deps
  // semantics don't always pick up an in-screen state change like the
  // null → uuid transition that happens after listConversations resolves.
  useEffect(() => {
    if (!conversationId) return undefined;
    let cancelled = false;
    setLoadingHistory(true);
    (async () => {
      const { success, data, error: err } = await apiService.getConversation(conversationId);
      if (cancelled) return;
      if (success) {
        setMessages(data.conversation?.messages || data.messages || []);
        setError('');
      } else {
        setError(err || 'No se pudo cargar la conversación');
      }
      setLoadingHistory(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // ActionCable subscription — separate effect with its own lifecycle so the
  // channel reconnects cleanly on conversationId change.
  useEffect(() => {
    if (!conversationId) return undefined;
    let mounted = true;
    console.log('[chat-effect] cable mount conv=', conversationId);

    const channel = new ChatChannel(conversationId);
    channelRef.current = channel;

    channel
      .on('delta', ({ content }) => {
        if (!mounted) return;
        setStreaming(true);
        setStreamBuffer((b) => b + (content || ''));
      })
      .on('message', ({ message }) => {
        if (!mounted || !message) return;
        setStreaming(false);
        setStreamBuffer('');
        setIsSending(false);
        setMessages((prev) => {
          if (prev.some((m) => m.id === message.id)) return prev;
          return [...prev, message];
        });
      })
      .on('done', () => {
        if (!mounted) return;
        setStreaming(false);
        setStreamBuffer('');
        setIsSending(false);
      })
      .on('error', ({ message }) => {
        if (!mounted) return;
        setStreaming(false);
        setStreamBuffer('');
        setIsSending(false);
        setError(message || 'Error en la conversación');
      });

    channel.connect();

    return () => {
      console.log('[chat-effect] cable cleanup conv=', conversationId);
      mounted = false;
      channel.disconnect();
      channelRef.current = null;
    };
  }, [conversationId]);

  // Auto-scroll on any change
  useEffect(() => {
    const id = setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(id);
  }, [messages.length, streamBuffer]);

  const handleSend = useCallback(
    async (content) => {
      if (!conversationId) {
        console.warn('[chat] handleSend called with no conversationId — message swallowed');
        return;
      }
      setError('');
      setLastFailedMessage(null);
      setIsSending(true);
      // Optimistic user message
      const optimistic = {
        id: `local-${Date.now()}`,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      const { success, data, error: err } = await apiService.postMessage(conversationId, content);
      if (!success) {
        setIsSending(false);
        setError(err || 'No se pudo enviar el mensaje. Verifica tu conexión.');
        setLastFailedMessage(content);
        // Roll back the optimistic message so the user sees the failure clearly
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        return;
      }
      const persisted = data.message || data;
      if (persisted?.id) {
        setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? persisted : m)));
      }
      // Assistant reply arrives over Cable
    },
    [conversationId],
  );

  const handleRetry = useCallback(() => {
    if (lastFailedMessage) handleSend(lastFailedMessage);
  }, [lastFailedMessage, handleSend]);

  const handleSelectConversation = useCallback(
    (id) => {
      setIsDrawerOpen(false);
      if (id === conversationId) return;
      navigation.navigate('Chat', { conversationId: id });
    },
    [navigation, conversationId],
  );

  const handleNewConversation = useCallback(
    (id) => {
      setIsDrawerOpen(false);
      navigation.navigate('Chat', { conversationId: id });
    },
    [navigation],
  );

  const avatarState =
    isSending && !streaming ? 'thinking' : streaming ? 'talking' : 'idle';

  // Don't gate the whole screen on loadingHistory — render the welcome
  // state immediately and let the messages slide in once they arrive.
  // (Previous behaviour: a full-screen spinner that hung if conversationId
  // was still null because listConversations hadn't resolved yet.)

  return (
    <SafeAreaView style={styles.rootContainer} edges={['top']}>
      <AvatarHeader
        avatarName={avatarName}
        avatar={user?.avatar}
        avatarState={avatarState}
        onModeChipPress={() => navigation.navigate('ProfileTab', { screen: 'ProfileHome' })}
        leftAction={
          <Pressable
            onPress={() => setIsDrawerOpen(true)}
            style={styles.headerButton}
            accessibilityRole="button"
            accessibilityLabel="Ver historial de conversaciones"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="chatbubbles-outline" size={22} color={colors.textPrimary} />
          </Pressable>
        }
      />

      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(it) => String(it.id)}
          renderItem={({ item }) => <MessageBubble message={item} />}
          contentContainerStyle={[
            styles.messagesList,
            messages.length === 0 && styles.messagesListEmpty,
          ]}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={<WelcomeMessage avatarName={avatarName} />}
          ListFooterComponent={
            <>
              <TypingIndicator isVisible={isSending && !streaming} />
              {streaming && streamBuffer ? (
                <View style={styles.streamingBubbleContainer}>
                  <View style={styles.streamingBubble}>
                    <MarkdownMessage content={streamBuffer} isUser={false} />
                    <View style={styles.streamingCursor} />
                  </View>
                </View>
              ) : null}
              {error ? <ErrorRetry message={error} onRetry={handleRetry} /> : null}
            </>
          }
          onContentSizeChange={() => {
            if (messages.length > 0) {
              listRef.current?.scrollToEnd({ animated: false });
            }
          }}
          onLayout={() => {
            if (messages.length > 0) {
              listRef.current?.scrollToEnd({ animated: false });
            }
          }}
        />

        <ChatInput onSend={handleSend} disabled={isSending || streaming} />
      </KeyboardAvoidingView>

      <ConversationDrawer
        isOpen={isDrawerOpen}
        activeConversationId={conversationId}
        onClose={() => setIsDrawerOpen(false)}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  rootContainer: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centerContainer: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
  },
  messagesList: {
    paddingVertical: spacing.sm,
  },
  messagesListEmpty: {
    flex: 1,
    justifyContent: 'center',
  },
  headerButton: {
    padding: spacing.xs,
  },
  welcomeContainer: {
    paddingHorizontal: spacing.xl,
    alignItems: 'center',
    gap: spacing.sm,
  },
  welcomeIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.elevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xs,
  },
  welcomeTitle: {
    fontSize: 24,
  },
  welcomeSubtitle: {
    lineHeight: 22,
    maxWidth: 300,
  },
  errorContainer: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xs,
    alignItems: 'flex-start',
  },
  errorBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.elevated,
    borderRadius: 12,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    gap: 6,
    borderWidth: 1,
    borderColor: colors.error,
  },
  errorText: {
    flex: 1,
    fontSize: typography.sizes.sm,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.xs,
    paddingVertical: 4,
  },
  streamingBubbleContainer: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xxs,
    alignItems: 'flex-start',
  },
  streamingBubble: {
    backgroundColor: colors.elevated,
    borderRadius: 16,
    borderBottomLeftRadius: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    maxWidth: '85%',
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  streamingCursor: {
    width: 2,
    height: 16,
    backgroundColor: colors.primary,
    marginLeft: 2,
    borderRadius: 1,
  },
});
