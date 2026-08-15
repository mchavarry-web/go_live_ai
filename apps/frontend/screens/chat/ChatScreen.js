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
  AppState,
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
import { playMessageAudio, stopMessageAudio } from '../../services/audioMessagePlayer';
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
  // ── History pagination (DEV-95) ──────────────────────────────────
  // getConversation now returns only the latest 30 messages; older pages
  // are lazy-loaded when the user scrolls to the top of the list.
  const [loadingOlder, setLoadingOlder] = useState(false);
  // Whether the server has messages older than our oldest loaded one.
  const hasMoreRef = useRef(false);
  // Re-entrancy guard so a burst of onScroll events near the top doesn't
  // fire overlapping page fetches.
  const loadingOlderRef = useRef(false);
  // While a prepend is settling, the scroll-to-end reactions (auto-scroll
  // effect + onContentSizeChange) must NOT fire — they'd yank the user
  // from the history they just pulled down to read.
  const prependingRef = useRef(false);
  // Mirror of `messages` so scroll handlers / loaders can read the current
  // list without being recreated on every message.
  const messagesRef = useRef([]);
  // Last scroll offset — lets us trigger "load older" only on genuine
  // upward scrolls, so the programmatic scrollToEnd on open (which passes
  // through low offsets going DOWN) can't fire a spurious page fetch.
  const lastScrollYRef = useRef(0);
  // Response watchdog. Started when a message POST succeeds, restarted by
  // the job's {type:"ack"} frame, cleared by the first delta / final
  // message / done / error from cable. Without it a stuck job (LLM hang,
  // dropped websocket, FastAPI timeout) leaves the spinner spinning
  // forever and the user can't retry.
  //
  // DEV-92: 60s (was 30s — staging telemetry shows legit first-token
  // latency of 30-37s), and expiry now REFETCHES before erroring: the
  // reply is usually persisted server-side seconds later, so recovering
  // it beats discarding the turn.
  const responseTimerRef = useRef(null);
  const RESPONSE_TIMEOUT_MS = 60_000;
  const clearResponseTimer = useCallback(() => {
    if (responseTimerRef.current) {
      clearTimeout(responseTimerRef.current);
      responseTimerRef.current = null;
    }
  }, []);

  // The persisted id of the user message whose reply we're waiting on.
  // Recovery only counts an assistant message that comes AFTER this one —
  // otherwise a failed send would get "recovered" by the previous turn's
  // reply and silently swallow the error.
  const awaitingUserMsgIdRef = useRef(null);

  // Refetch the conversation and, if the assistant reply already landed
  // (it's persisted before the cable frames go out), render it and clear
  // the in-flight state. Returns true when a reply was recovered. Used by
  // the watchdog, by Reintentar (so retry never duplicates a turn that
  // actually completed), and after a cable resubscribe (frames broadcast
  // while the socket was down are lost forever).
  const recoverMissedReply = useCallback(async () => {
    const awaitedId = awaitingUserMsgIdRef.current;
    if (!conversationId || !awaitedId) return false;
    const { success, data } = await apiService.getConversation(conversationId);
    if (!success) return false;
    const list = data.conversation?.messages || data.messages || [];
    const idx = list.findIndex((m) => String(m.id) === String(awaitedId));
    if (idx === -1) return false;
    const reply = list.slice(idx + 1).find((m) => m.role === 'assistant');
    if (!reply) return false;
    awaitingUserMsgIdRef.current = null;
    // getConversation only returns the LATEST page (DEV-95) — don't wipe
    // older pages the user already lazy-loaded. Keep every already-loaded
    // message that precedes the refetched window (dedupe by id), then
    // append the fresh window.
    setMessages((prev) => {
      const windowIds = new Set(list.map((m) => String(m.id)));
      const older = [];
      for (const m of prev) {
        if (windowIds.has(String(m.id))) break; // reached the refetched window
        if (String(m.id).startsWith('local-')) continue; // optimistic leftovers
        older.push(m);
      }
      // Only trust the refetch's has_more flag when we hold no extra pages;
      // otherwise our local oldest is older than the window's boundary and
      // the flag would wrongly re-arm (dedupe makes a stray fetch harmless,
      // but skipping it is cheaper).
      if (older.length === 0) {
        hasMoreRef.current = !!data.conversation?.has_more_messages;
      }
      return [...older, ...list];
    });
    setStreaming(false);
    setStreamBuffer('');
    setIsSending(false);
    setError('');
    setLastFailedMessage(null);
    return true;
  }, [conversationId]);

  const startResponseTimer = useCallback(() => {
    clearResponseTimer();
    responseTimerRef.current = setTimeout(async () => {
      responseTimerRef.current = null;
      const recovered = await recoverMissedReply();
      if (recovered) return;
      setStreaming(false);
      setStreamBuffer('');
      setIsSending(false);
      setError('La respuesta tardó demasiado. Toca Reintentar.');
    }, RESPONSE_TIMEOUT_MS);
  }, [clearResponseTimer, recoverMissedReply]);

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
      hasMoreRef.current = false;
      loadingOlderRef.current = false;
      prependingRef.current = false;
      setLoadingOlder(false);
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
    hasMoreRef.current = false;
    (async () => {
      const { success, data, error: err } = await apiService.getConversation(conversationId);
      if (cancelled) return;
      if (success) {
        // Latest page only (DEV-95); older history lazy-loads on scroll-up.
        setMessages(data.conversation?.messages || data.messages || []);
        hasMoreRef.current = !!data.conversation?.has_more_messages;
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

  // Keep messagesRef in sync so scroll handlers can read the current list
  // without re-subscribing on every render.
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Fetch the page of messages older than the oldest one on screen and
  // prepend it. maintainVisibleContentPosition on the FlatList keeps the
  // viewport anchored on the row the user was reading while rows appear
  // above it.
  const loadOlderMessages = useCallback(async () => {
    if (!conversationId || loadingOlderRef.current || !hasMoreRef.current) return;
    const oldest = messagesRef.current.find((m) => !String(m.id).startsWith('local-'));
    if (!oldest) return;
    loadingOlderRef.current = true;
    prependingRef.current = true;
    setLoadingOlder(true);
    try {
      const { success, data } = await apiService.getMessages(conversationId, { before: oldest.id });
      if (success) {
        hasMoreRef.current = !!data.has_more;
        const older = data.messages || [];
        if (older.length > 0) {
          setMessages((prev) => {
            const seen = new Set(prev.map((m) => String(m.id)));
            const fresh = older.filter((m) => !seen.has(String(m.id)));
            return fresh.length > 0 ? [...fresh, ...prev] : prev;
          });
        }
      }
    } finally {
      loadingOlderRef.current = false;
      setLoadingOlder(false);
      // Release the scroll-to-end guard once the prepended rows have
      // rendered and mVCP has re-anchored the viewport.
      setTimeout(() => {
        prependingRef.current = false;
      }, 250);
    }
  }, [conversationId]);

  // Trigger "load older" only on a genuine upward scroll near the top —
  // the offset check alone would also match the programmatic scrollToEnd
  // pass on open (it sweeps through low offsets heading DOWN).
  const handleScroll = useCallback(
    ({ nativeEvent }) => {
      const y = nativeEvent.contentOffset.y;
      const scrollingUp = y < lastScrollYRef.current;
      lastScrollYRef.current = y;
      if (scrollingUp && y < 80) loadOlderMessages();
    },
    [loadOlderMessages],
  );

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
        // First token: tokens are flowing, drop the watchdog. A mid-stream
        // stall after this point will surface as a websocket close, not a
        // 30s timeout (avoids nuking partial output the user is reading).
        clearResponseTimer();
        setStreaming(true);
        setStreamBuffer((b) => b + (content || ''));
      })
      .on('message', ({ message }) => {
        if (!mounted || !message) return;
        clearResponseTimer();
        awaitingUserMsgIdRef.current = null;
        setStreaming(false);
        setStreamBuffer('');
        setIsSending(false);
        setLastFailedMessage(null);
        // A late reply after the watchdog already fired: the error banner
        // must not outlive the answer it was complaining about.
        setError('');
        setMessages((prev) => {
          if (prev.some((m) => m.id === message.id)) return prev;
          return [...prev, message];
        });
      })
      // Job picked up by Sidekiq — generation is genuinely running, so
      // restart the watchdog: queue wait shouldn't eat generation budget.
      .on('ack', () => {
        if (!mounted) return;
        if (responseTimerRef.current) startResponseTimer();
      })
      // Subscription re-confirmed after a drop. Anything broadcast while
      // the socket was down is gone — refetch so an in-flight turn's
      // reply (or any missed message) isn't lost.
      .on('resubscribed', () => {
        if (!mounted) return;
        recoverMissedReply();
      })
      .on('done', () => {
        if (!mounted) return;
        clearResponseTimer();
        setStreaming(false);
        setStreamBuffer('');
        setIsSending(false);
      })
      .on('error', ({ message }) => {
        if (!mounted) return;
        clearResponseTimer();
        setStreaming(false);
        setStreamBuffer('');
        setIsSending(false);
        setError(message || 'Error en la conversación');
      })
      // Audio frame: emitted by ChatGenerationJob after the assistant
      // text has been broadcast and the TTS bytes have been attached.
      // We auto-play immediately so the avatar "speaks back" — no tap
      // required. The play button on the bubble is just a replay.
      .on('audio', ({ assistant_message_id }) => {
        console.log('[chat] audio frame for message=', assistant_message_id);
        if (!mounted || !assistant_message_id) return;
        // Mark the persisted message as has_audio so MessageBubble shows
        // the replay button without waiting for a re-fetch.
        setMessages((prev) => prev.map((m) => (
          m.id === assistant_message_id ? { ...m, has_audio: true } : m
        )));
        playMessageAudio(assistant_message_id).then((ok) => {
          console.log('[chat] auto-play result=', ok);
        }).catch((err) => {
          console.warn('[chat] auto-play failed', err?.message);
        });
      });

    channel.connect();

    // Foregrounding the app: kick the channel so it doesn't have to wait
    // for the next exponential-backoff slot. The OS often closes the
    // socket while the app is suspended; without this, users coming back
    // from lock would see a stale "websocket error" until the next retry.
    const appStateSub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        channel.forceReconnect();
      }
    });

    return () => {
      console.log('[chat-effect] cable cleanup conv=', conversationId);
      mounted = false;
      clearResponseTimer();
      appStateSub.remove();
      channel.disconnect();
      channelRef.current = null;
      // Cut off any in-progress TTS so it doesn't keep playing when the
      // user navigates away from the conversation.
      stopMessageAudio();
    };
  }, [conversationId, clearResponseTimer, startResponseTimer, recoverMissedReply]);

  // Auto-scroll on any change — except while older history is being
  // prepended (messages.length grows then too, and scrolling to end would
  // rip the user away from what they scrolled up to read).
  useEffect(() => {
    if (prependingRef.current) return undefined;
    const id = setTimeout(() => {
      if (!prependingRef.current) listRef.current?.scrollToEnd({ animated: true });
    }, 50);
    return () => clearTimeout(id);
  }, [messages.length, streamBuffer]);

  const handleSend = useCallback(
    async (content) => {
      if (!conversationId) {
        console.warn('[chat] handleSend called with no conversationId — message swallowed');
        return;
      }
      setError('');
      // If the OS killed the socket (backgrounding, network blip), kick a
      // reconnect BEFORE the reply starts broadcasting — cable frames are
      // fire-and-forget and anything sent while we're down is lost.
      channelRef.current?.forceReconnect();
      // Remember the content while the response is in flight so a
      // timeout / cable error can offer the user a retry. Cleared when
      // the assistant message lands.
      setLastFailedMessage(content);
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
        // Roll back the optimistic message so the user sees the failure clearly
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        return;
      }
      const persisted = data.message || data;
      if (persisted?.id) {
        setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? persisted : m)));
      }
      // Assistant reply arrives over Cable. Start the watchdog so a
      // never-arriving response can't strand the spinner; on expiry it
      // refetches before erroring (see startResponseTimer).
      awaitingUserMsgIdRef.current = persisted?.id || null;
      startResponseTimer();
    },
    [conversationId, startResponseTimer],
  );

  const handleSendVoice = useCallback(
    async ({ uri, mime, durationSeconds }) => {
      if (!conversationId) {
        console.warn('[chat] handleSendVoice called with no conversationId — message swallowed');
        return;
      }
      setError('');
      setIsSending(true);
      // Optimistic placeholder: the transcript only lands once Rails
      // finishes the synchronous transcribe hop, so we render a
      // "🎤 …" pending bubble in the meantime so the user sees their
      // input was accepted.
      const optimistic = {
        id: `local-voice-${Date.now()}`,
        role: 'user',
        content: '🎤 …',
        metadata: { voice_input: true, pending: true, durationSeconds },
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);

      const { success, data, error: err } = await apiService.postVoiceMessage(
        conversationId,
        { uri, mime },
      );
      if (!success) {
        setIsSending(false);
        setError(err || 'No se pudo enviar el audio. Intenta de nuevo.');
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        return;
      }
      const persisted = data.message || data;
      if (persisted?.id) {
        setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? persisted : m)));
      }
      // Watchdog parallels the text path.
      awaitingUserMsgIdRef.current = persisted?.id || null;
      startResponseTimer();
    },
    [conversationId, startResponseTimer],
  );

  // Recover-first retry: if the reply actually landed (watchdog fired
  // while generation was merely slow), render it instead of re-sending —
  // re-POSTing would generate a duplicate assistant turn and double the
  // mode message counter.
  const handleRetry = useCallback(async () => {
    setError('');
    const recovered = await recoverMissedReply();
    if (!recovered && lastFailedMessage) handleSend(lastFailedMessage);
  }, [recoverMissedReply, lastFailedMessage, handleSend]);

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
          renderItem={({ item }) => (
            <MessageBubble message={item} isTester={!!user?.is_tester} />
          )}
          contentContainerStyle={[
            styles.messagesList,
            messages.length === 0 && styles.messagesListEmpty,
          ]}
          showsVerticalScrollIndicator={false}
          // Prepending older pages must not shift what the user is looking
          // at: keep the first visible row anchored while rows are inserted
          // above it (supported for plain lists on RN 0.7x).
          maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
          onScroll={handleScroll}
          scrollEventThrottle={100}
          ListEmptyComponent={<WelcomeMessage avatarName={avatarName} />}
          ListHeaderComponent={
            loadingOlder ? (
              <View style={styles.loadOlderContainer}>
                <ActivityIndicator size="small" color={colors.primary} />
              </View>
            ) : null
          }
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
            if (messages.length > 0 && !prependingRef.current) {
              listRef.current?.scrollToEnd({ animated: false });
            }
          }}
          onLayout={() => {
            if (messages.length > 0 && !prependingRef.current) {
              listRef.current?.scrollToEnd({ animated: false });
            }
          }}
        />

        <ChatInput
          onSend={handleSend}
          onSendVoice={handleSendVoice}
          disabled={isSending || streaming}
        />
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
  loadOlderContainer: {
    paddingVertical: spacing.sm,
    alignItems: 'center',
    justifyContent: 'center',
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
