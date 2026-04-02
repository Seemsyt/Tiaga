import React from 'react';
import {Box, Text} from 'ink';

type StatusBarProps = {
  busy: boolean;
  modeLabel: string;
};

export function StatusBar({busy, modeLabel}: StatusBarProps) {
  return (
    <Box justifyContent="space-between">
      <Text dimColor>Enter send  Esc+Enter newline  /help commands  Ctrl+C exit</Text>
      <Text color={busy ? 'yellow' : 'green'}>{busy ? 'streaming' : modeLabel}</Text>
    </Box>
  );
}
