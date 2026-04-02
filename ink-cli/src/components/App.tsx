import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {Box, Text, useApp} from 'ink';
import {handleSlashCommand} from '../commands/slash.js';
import {
  createEngineStream,
  listSessions,
  loadHistory
} from '../engine/pythonBridge.js';
import type {ChatMessage, SessionSummary} from '../types.js';
import {PromptInput} from './input/PromptInput.js';
import {Header} from './layout/Header.js';
import {StatusBar} from './layout/StatusBar.js';
import {MessageList} from './messages/MessageList.js';
import {SessionPicker} from './session/SessionPicker.js';
import {Divider} from './ui/Divider.js';

type AppProps = {
  initialSession?: string;
};

const makeId = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const engineStream = createEngineStream();

export function App({initialSession}: AppProps) {
  const {exit} = useApp();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [currentSession, setCurrentSession] = useState<string | null>(initialSession ?? null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState('ready');

  const cwd = useMemo(() => process.cwd().replace(process.env.HOME ?? '', '~'), []);

  const refreshSessions = useCallback(async () => {
    try {
      const nextSessions = await listSessions();
      setSessions(nextSessions);
      setStatusMessage('ready');
    } catch (error) {
      setStatusMessage('bridge unavailable');
      setMessages([
        {
          id: makeId('error'),
          role: 'meta',
          content: `Failed to load sessions: ${String(error)}`
        }
      ]);
    } finally {
      setSessionsLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    if (!currentSession) {
      return;
    }

    let cancelled = false;

    const hydrate = async () => {
      try {
        const history = await loadHistory(currentSession);
        if (!cancelled) {
          setMessages(history);
          setStatusMessage('ready');
        }
      } catch (error) {
        if (!cancelled) {
          setMessages([
            {
              id: makeId('error'),
              role: 'meta',
              content: `Failed to load history: ${String(error)}`
            }
          ]);
          setStatusMessage('history unavailable');
        }
      }
    };

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, [currentSession]);

  const appendMessages = useCallback((nextMessages: ChatMessage[]) => {
    setMessages(current => [...current, ...nextMessages]);
  }, []);

  const updateStreamingMessage = useCallback((delta: string) => {
    setMessages(current =>
      current.map(message =>
        message.role === 'assistant' && message.streaming
          ? {...message, content: message.content + delta}
          : message
      )
    );
  }, []);

  const closeStreamingMessage = useCallback(() => {
    setMessages(current =>
      current.map(message =>
        message.role === 'assistant' && message.streaming
          ? {...message, streaming: false}
          : message
      )
    );
  }, []);

  const threadId = useMemo(
    () => currentSession ?? `session-${Date.now()}`,
    [currentSession]
  );

  const handleSubmit = useCallback(
    async (value: string) => {
      const slash = handleSlashCommand(value);

      if (slash.kind === 'quit') {
        exit();
        return;
      }

      if (slash.kind === 'clear') {
        setMessages([]);
        return;
      }

      if (slash.kind === 'messages') {
        appendMessages(slash.messages);
        return;
      }

      if (!currentSession) {
        setCurrentSession(threadId);
      }

      const userMessage: ChatMessage = {
        id: makeId('user'),
        role: 'user',
        content: value
      };

      setBusy(true);
      setStatusMessage('streaming');
      setMessages(current => [...current, userMessage]);

      try {
        for await (const event of engineStream(value, threadId)) {
          if (event.type === 'text_start') {
            appendMessages([
              {
                id: makeId('assistant'),
                role: 'assistant',
                content: '',
                streaming: true
              }
            ]);
            continue;
          }

          if (event.type === 'tool_start') {
            appendMessages([
              {
                id: makeId('tool-call'),
                role: 'tool_call',
                name: event.name,
                content: event.inputPreview
              }
            ]);
            continue;
          }

          if (event.type === 'tool_end') {
            appendMessages([
              {
                id: makeId('tool-result'),
                role: 'tool_result',
                content: event.resultPreview
              }
            ]);
            continue;
          }

          if (event.type === 'text_delta') {
            updateStreamingMessage(event.delta);
            continue;
          }

          if (event.type === 'done') {
            closeStreamingMessage();
            setBusy(false);
            setStatusMessage('ready');
            void refreshSessions();
            continue;
          }

          if (event.type === 'error') {
            appendMessages([
              {
                id: makeId('error'),
                role: 'meta',
                content: `Error: ${event.error}`
              }
            ]);
            closeStreamingMessage();
            setBusy(false);
            setStatusMessage('bridge error');
          }
        }
      } catch (error) {
        appendMessages([
          {
            id: makeId('error'),
            role: 'meta',
            content: `Bridge error: ${String(error)}`
          }
        ]);
        closeStreamingMessage();
        setBusy(false);
        setStatusMessage('bridge error');
      }
    },
    [
      appendMessages,
      closeStreamingMessage,
      currentSession,
      exit,
      refreshSessions,
      threadId,
      updateStreamingMessage
    ]
  );

  if (!currentSession) {
    if (!sessionsLoaded) {
      return <Text dimColor>Loading sessions...</Text>;
    }

    return (
      <Box flexDirection="column">
        {statusMessage !== 'ready' ? <Text color="yellow">{statusMessage}</Text> : null}
        <SessionPicker sessions={sessions} onSelect={setCurrentSession} />
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <Header model="openrouter" cwd={cwd} sessionName={currentSession} />
      <Divider />
      <MessageList messages={messages} />
      <Divider />
      <PromptInput disabled={busy} onSubmit={handleSubmit} />
      <Divider />
      <StatusBar busy={busy} modeLabel={statusMessage} />
      <Text dimColor>Bridge: tiaga.bridge</Text>
    </Box>
  );
}
