"""Bounded Qwen SSE decoding and complete-question publication. No I/O or SDK."""
import json
import time


class QuestionStream:
    """Only emit closed JSON objects directly inside the top-level questions array."""
    def __init__(self, callback):
        self.callback = callback
        self.text = ''
        self.pos = 0
        self.stack = []
        self.quoted = False
        self.escaped = False
        self.string_start = 0
        self.key = None
        self.questions_depth = None
        self.object_start = None
        self.items = []
        self.closed = False

    def feed(self, piece):
        self.text += piece
        if len(self.text) > 2_000_000:
            raise ValueError('AI stream too large')
        for i in range(self.pos, len(self.text)):
            c = self.text[i]
            if self.quoted:
                if self.escaped:
                    self.escaped = False
                elif c == '\\':
                    self.escaped = True
                elif c == '"':
                    self.quoted = False
                    if len(self.stack) == 1 and self.stack[0] == '{':
                        self.key = json.loads(self.text[self.string_start:i+1])
                continue
            if c == '"':
                self.quoted = True
                self.string_start = i
            elif c in '{[':
                if c == '[' and self.key == 'questions' and self.stack == ['{']:
                    if self.questions_depth is not None or self.closed:
                        raise ValueError('Duplicate questions array')
                    self.questions_depth = 2
                    self.key = None
                if c == '{' and self.questions_depth is not None and len(self.stack) == self.questions_depth:
                    self.object_start = i
                self.stack.append(c)
            elif c in '}]':
                if not self.stack or self.stack[-1] != ('{' if c == '}' else '['):
                    raise ValueError('Invalid JSON nesting')
                if c == '}' and self.object_start is not None and len(self.stack) == self.questions_depth + 1:
                    value = json.loads(self.text[self.object_start:i+1])
                    if not isinstance(value, dict) or len(self.items) >= 60:
                        raise ValueError('Invalid streamed questions')
                    self.items.append(value)
                    self.object_start = None
                    # Give consumers immutable snapshots; normalisation may mutate them.
                    self.callback(json.loads(json.dumps({'questions': self.items, 'note': ''})))
                if c == ']' and self.questions_depth is not None and len(self.stack) == self.questions_depth:
                    self.closed = True
                    self.questions_depth = None
                self.stack.pop()
            elif c == ',' and self.stack == ['{']:
                self.key = None
        self.pos = len(self.text)


def read_qwen_stream(response, timeout, on_partial=None):
    """Return the ordinary completion shape so usage/error handling stays shared."""
    deadline = time.monotonic() + timeout
    parser = QuestionStream(on_partial) if on_partial else None
    pieces = []
    usage = None
    finish = None
    size = 0
    for raw in iter(lambda: response.readline(1_048_577), b''):
        if time.monotonic() > deadline:
            raise TimeoutError('AI stream deadline exceeded')
        size += len(raw)
        if len(raw) > 1_048_576 or size > 4_000_000:
            raise ValueError('AI stream too large')
        line = raw.decode('utf-8').strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if payload == '[DONE]':
            break
        event = json.loads(payload)
        if event.get('error'):
            raise ValueError('AI stream provider error')
        if event.get('usage'):
            usage = event['usage']
        for choice in event.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            if choice.get('finish_reason'):
                finish = choice['finish_reason']
            delta = choice.get('delta', {})
            if delta.get('refusal'):
                raise ValueError('AI stream refusal')
            content = delta.get('content')
            if content:
                if not isinstance(content, str):
                    raise ValueError('Invalid AI stream content')
                pieces.append(content)
                if parser:
                    parser.feed(content)
    return {'choices': [{'finish_reason': finish, 'message': {'content': ''.join(pieces)}}], 'usage': usage or {}}
