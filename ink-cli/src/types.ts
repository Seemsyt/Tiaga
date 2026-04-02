export type SessionSummary = {
  id: string;
  updatedAt?: string;
};

export type ChatMessage =
  | {
      id: string;
      role: 'user' | 'assistant' | 'meta';
      content: string;
      streaming?: boolean;
    }
  | {
      id: string;
      role: 'tool_call';
      name: string;
      content: string;
    }
  | {
      id: string;
      role: 'tool_result';
      content: string;
    };

export type StreamEvent =
  | {type: 'text_start'}
  | {type: 'text_delta'; delta: string}
  | {type: 'tool_start'; name: string; inputPreview: string}
  | {type: 'tool_end'; resultPreview: string}
  | {type: 'done'}
  | {type: 'error'; error: string};
