"""
Token → sentence adaptor. Buffers deltas until a sentence terminator
(`.`, `!`, `?`) followed by whitespace. Trailing non-terminated text
is flushed on stream close.

Implementation note: during streaming the regex uses ``\\s`` rather than
``(?:\\s|$)`` because ``$`` would match the current buffer's end on every
iteration, causing premature cuts on tokens like "Fine." before the
next token has arrived. The final ``buf.strip()`` flush at end-of-stream
handles genuine EOF.
"""
from __future__ import annotations

import re
from typing import AsyncIterator

_SENTENCE_END = re.compile(r'[.!?]\s')


async def sentence_stream(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    buf = ""
    async for tok in token_stream:
        buf += tok
        while True:
            m = _SENTENCE_END.search(buf)
            if not m:
                break
            cut = m.end()
            sentence = buf[:cut].strip()
            if sentence:
                yield sentence
            buf = buf[cut:]
    if buf.strip():
        yield buf.strip()
