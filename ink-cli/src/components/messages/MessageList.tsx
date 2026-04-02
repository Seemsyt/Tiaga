import React from 'react';
import {Box, Static, Text} from 'ink';
import type {ChatMessage} from '../../types.js';
import {Spinner} from '../ui/Spinner.js';

type MessageListProps = {
  messages: ChatMessage[];
};

const renderBody = (content: string) => {
  const lines = content.length > 0 ? content.split('\n') : [''];
  return lines.map((line, index) => (
    <Text key={index}>{`  ${line}`}</Text>
  ));
};

function MessageRow({message}: {message: ChatMessage}) {
  if (message.role === 'user') {
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Text bold color="cyan">You</Text>
        {renderBody(message.content)}
      </Box>
    );
  }

  if (message.role === 'assistant') {
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Box>
          <Text bold color="green">Tiaga</Text>
          <Text> </Text>
          {message.streaming ? <Spinner /> : null}
        </Box>
        {renderBody(message.content)}
      </Box>
    );
  }

  if (message.role === 'tool_call') {
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Text bold color="yellow">{`⚙ ${message.name}`}</Text>
        <Text dimColor>{`  › ${message.content}`}</Text>
      </Box>
    );
  }

  if (message.role === 'tool_result') {
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Text dimColor>{`└─ ${message.content}`}</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text dimColor>Info</Text>
      {renderBody(message.content)}
    </Box>
  );
}

export function MessageList({messages}: MessageListProps) {
  const completedMessages = messages.filter(message => !message.streaming);
  const liveMessage = messages.findLast(message => message.streaming);

  return (
    <Box flexDirection="column">
      <Static items={completedMessages}>
        {message => <MessageRow key={message.id} message={message} />}
      </Static>
      {liveMessage ? <MessageRow message={liveMessage} /> : null}
    </Box>
  );
}
