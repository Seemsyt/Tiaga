import {spawn} from 'child_process';
import * as readline from 'readline';
import type {ChatMessage, SessionSummary, StreamEvent} from '../types.js';

type BridgeHistoryMessage = {
  role: 'user' | 'assistant';
  content: string;
};

type BridgeResponse =
  | {type: 'session_list'; sessions: SessionSummary[]}
  | {type: 'history'; messages: BridgeHistoryMessage[]}
  | {type: 'error'; error: string};

export type EngineStream = (
  input: string,
  threadId: string
) => AsyncGenerator<StreamEvent>;

const makeId = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

function spawnBridge() {
  return spawn('python3', ['-u', '-m', 'tiaga.bridge'], {
    cwd: process.cwd(),
    env: process.env,
    stdio: ['pipe', 'pipe', 'inherit']
  });
}

async function requestBridge(payload: object): Promise<BridgeResponse> {
  const bridge = spawnBridge();

  return await new Promise((resolve, reject) => {
    let stdout = '';
    let settled = false;
    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        bridge.kill();
        reject(new Error('Bridge request timed out'));
      }
    }, 10000);

    bridge.stdout.setEncoding('utf8');
    bridge.stdout.on('data', chunk => {
      stdout += chunk;
    });

    bridge.on('error', error => {
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        reject(error);
      }
    });

    bridge.on('close', code => {
      if (settled) {
        return;
      }

      settled = true;
      clearTimeout(timeout);

      if (code !== 0 && stdout.trim().length === 0) {
        reject(new Error(`Bridge exited with code ${code}`));
        return;
      }

      const line = stdout
        .split('\n')
        .map(item => item.trim())
        .find(Boolean);

      if (!line) {
        reject(new Error('Bridge returned no data'));
        return;
      }

      try {
        resolve(JSON.parse(line) as BridgeResponse);
      } catch (error) {
        reject(error);
      }
    });

    bridge.stdin.write(`${JSON.stringify(payload)}\n`);
    bridge.stdin.end();
  });
}

export async function listSessions(): Promise<SessionSummary[]> {
  const response = await requestBridge({action: 'list_sessions'});
  if (response.type === 'error') {
    throw new Error(response.error);
  }
  return response.sessions;
}

export async function loadHistory(threadId: string): Promise<ChatMessage[]> {
  const response = await requestBridge({action: 'get_history', thread_id: threadId});
  if (response.type === 'error') {
    throw new Error(response.error);
  }

  return response.messages.map(message => ({
    id: makeId(message.role),
    role: message.role,
    content: message.content
  }));
}

export function createEngineStream(): EngineStream {
  return streamFromPython;
}

async function* streamFromPython(
  input: string,
  threadId: string
): AsyncGenerator<StreamEvent> {
  const bridge = spawnBridge();
  const rl = readline.createInterface({input: bridge.stdout, crlfDelay: Infinity});

  bridge.stdin.write(
    `${JSON.stringify({action: 'chat', message: input, thread_id: threadId})}\n`
  );
  bridge.stdin.end();

  try {
    yield {type: 'text_start'};

    for await (const line of rl) {
      if (!line.trim()) {
        continue;
      }

      try {
        const event = JSON.parse(line) as StreamEvent;
        yield event;
        if (event.type === 'done' || event.type === 'error') {
          break;
        }
      } catch (error) {
        yield {type: 'error', error: `Parse error: ${String(error)}`};
        break;
      }
    }
  } finally {
    rl.close();
    bridge.kill();
  }
}
