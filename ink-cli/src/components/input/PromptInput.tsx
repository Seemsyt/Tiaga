import React, {useEffect, useState} from 'react';
import {Box, Text, useInput} from 'ink';

type PromptInputProps = {
  disabled?: boolean;
  onSubmit: (value: string) => void;
};

export function PromptInput({disabled = false, onSubmit}: PromptInputProps) {
  const [value, setValue] = useState('');
  const [escapeArmed, setEscapeArmed] = useState(false);

  useEffect(() => {
    if (disabled) {
      setEscapeArmed(false);
    }
  }, [disabled]);

  useInput((input, key) => {
    if (disabled) {
      return;
    }

    if (key.escape) {
      setEscapeArmed(true);
      return;
    }

    if (key.return) {
      if (escapeArmed) {
        setValue(current => `${current}\n`);
        setEscapeArmed(false);
        return;
      }

      const trimmed = value.trim();
      if (!trimmed) {
        return;
      }

      onSubmit(value);
      setValue('');
      return;
    }

    if (key.backspace || key.delete) {
      setValue(current => current.slice(0, -1));
      setEscapeArmed(false);
      return;
    }

    if (key.ctrl && input === 'u') {
      setValue('');
      setEscapeArmed(false);
      return;
    }

    if (input) {
      setValue(current => current + input);
      setEscapeArmed(false);
    }
  });

  const lines = (value.length > 0 ? value : '').split('\n');
  const visibleLines = lines.length > 0 ? lines : [''];
  const lastIndex = visibleLines.length - 1;

  return (
    <Box flexDirection="column">
      {visibleLines.map((line, index) => (
        <Text key={index}>
          <Text dimColor>{index === 0 ? '> ' : '  '}</Text>
          <Text>{line}</Text>
          {index === lastIndex ? <Text inverseColor> </Text> : null}
        </Text>
      ))}
      {disabled ? <Text dimColor>  waiting for response…</Text> : null}
    </Box>
  );
}
