import React from 'react';
import {Box, Text} from 'ink';

type HeaderProps = {
  model: string;
  cwd: string;
  sessionName: string;
};

export function Header({model, cwd, sessionName}: HeaderProps) {
  return (
    <Box justifyContent="space-between">
      <Text>
        <Text bold color="cyan">◆ tiaga</Text>
        <Text dimColor>  │  </Text>
        <Text>{model}</Text>
      </Text>
      <Text>
        <Text dimColor>{cwd}</Text>
        <Text dimColor>  │  </Text>
        <Text>{sessionName}</Text>
      </Text>
    </Box>
  );
}
