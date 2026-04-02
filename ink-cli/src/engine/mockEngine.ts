import type {StreamEvent} from '../types.js';

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

const buildMockAnswer = (input: string): string => {
  if (input.toLowerCase().includes('claude')) {
    return [
      'We can get much closer to the Claude Code feel with Ink than with prompt_toolkit.',
      '',
      'Next steps:',
      '- Freeze the Python UI and start migrating the terminal surface to React components.',
      '- Keep the Python agent loop temporarily and bridge it into typed stream events.',
      '- Replace the mock engine with a real transport once the layout feels right.'
    ].join('\n');
  }

  return [
    `Working on: ${input}`,
    '',
    'This Ink scaffold is live-ready for transcript rendering, slash commands, and tool activity.',
    'The next integration step is streaming real events from the Python backend.'
  ].join('\n');
};

export async function* streamMockTurn(input: string): AsyncGenerator<StreamEvent> {
  const answer = buildMockAnswer(input);

  if (input.toLowerCase().includes('file') || input.toLowerCase().includes('project')) {
    yield {
      type: 'tool_start',
      name: 'list_files',
      inputPreview: '.'
    };
    await wait(250);
    yield {
      type: 'tool_end',
      resultPreview: 'Scanned project root and prepared UI migration targets.'
    };
    await wait(150);
  }

  yield {type: 'text_start'};
  await wait(120);

  for (const token of answer.split(/(\s+)/)) {
    if (!token) {
      continue;
    }

    yield {type: 'text_delta', delta: token};
    await wait(20);
  }

  yield {type: 'done'};
}
