import type {ChatMessage} from '../types.js';

export type SlashAction =
  | {kind: 'continue'}
  | {kind: 'messages'; messages: ChatMessage[]}
  | {kind: 'clear'}
  | {kind: 'quit'};

export const HELP_TEXT = [
  '/help    list available commands',
  '/clear   clear the current transcript',
  '/compact placeholder for future context compaction',
  '/cost    placeholder for future token usage reporting',
  '/quit    exit the CLI'
].join('\n');

export function handleSlashCommand(input: string): SlashAction {
  const command = input.trim().toLowerCase();

  if (!command.startsWith('/')) {
    return {kind: 'continue'};
  }

  switch (command) {
    case '/help':
      return {
        kind: 'messages',
        messages: [
          {
            id: `meta-${Date.now()}`,
            role: 'meta',
            content: HELP_TEXT
          }
        ]
      };
    case '/clear':
      return {kind: 'clear'};
    case '/compact':
      return {
        kind: 'messages',
        messages: [
          {
            id: `meta-${Date.now()}`,
            role: 'meta',
            content: 'Context compaction is planned, but there is no CLI command for it yet.'
          }
        ]
      };
    case '/cost':
      return {
        kind: 'messages',
        messages: [
          {
            id: `meta-${Date.now()}`,
            role: 'meta',
            content: 'Token and cost reporting is not implemented in the current bridge.'
          }
        ]
      };
    case '/quit':
      return {kind: 'quit'};
    default:
      return {
        kind: 'messages',
        messages: [
          {
            id: `meta-${Date.now()}`,
            role: 'meta',
            content: `Unknown command: ${input.trim()}`
          }
        ]
      };
  }
}
