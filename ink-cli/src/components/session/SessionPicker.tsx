import React, {useMemo, useState} from 'react';
import {Box, Text, useInput} from 'ink';
import type {SessionSummary} from '../../types.js';

type SessionPickerProps = {
  sessions: SessionSummary[];
  onSelect: (sessionId: string) => void;
};

function formatRelative(isoDate?: string) {
  if (!isoDate) {
    return 'saved session';
  }

  const diffMs = Date.now() - new Date(isoDate).getTime();
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));

  if (diffHours <= 1) {
    return 'just now';
  }

  if (diffHours < 24) {
    return `${diffHours} hours ago`;
  }

  const diffDays = Math.round(diffHours / 24);
  return diffDays === 1 ? 'yesterday' : `${diffDays} days ago`;
}

export function SessionPicker({sessions, onSelect}: SessionPickerProps) {
  const items = useMemo(
    () => [...sessions, {id: '[new session]', updatedAt: new Date().toISOString()}],
    [sessions]
  );
  const [selectedIndex, setSelectedIndex] = useState(0);

  useInput((input, key) => {
    if (key.upArrow) {
      setSelectedIndex(current => Math.max(0, current - 1));
      return;
    }

    if (key.downArrow) {
      setSelectedIndex(current => Math.min(items.length - 1, current + 1));
      return;
    }

    if (input === 'n') {
      onSelect(`session-${Date.now()}`);
      return;
    }

    if (key.return) {
      const selected = items[selectedIndex];
      onSelect(selected.id === '[new session]' ? `session-${Date.now()}` : selected.id);
    }
  });

  return (
    <Box flexDirection="column">
      <Text bold color="cyan">◆ tiaga — select session</Text>
      <Text> </Text>
      {items.map((session, index) => {
        const active = index === selectedIndex;
        const prefix = active ? '> ' : '  ';
        const label = session.id.padEnd(18, ' ');
        return (
          <Text key={session.id} color={active ? 'cyan' : undefined}>
            {prefix}
            {label}
            <Text dimColor>{session.id === '[new session]' ? '' : formatRelative(session.updatedAt)}</Text>
          </Text>
        );
      })}
      <Text> </Text>
      <Text dimColor>↑↓ navigate  Enter open  n new  Ctrl+C exit</Text>
    </Box>
  );
}
