from __future__ import annotations

import asyncio
import pytest

from services.sentence_stream import sentence_stream


async def _iter(tokens):
    for t in tokens:
        yield t
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_splits_on_sentence_terminators():
    tokens = ["Hello", " world", ".", " How", " are", " you", "?", " Fine", "."]
    out = [s async for s in sentence_stream(_iter(tokens))]
    assert out == ["Hello world.", "How are you?", "Fine."]


@pytest.mark.asyncio
async def test_flushes_trailing_fragment_without_terminator():
    tokens = ["incomplete", " fragment"]
    out = [s async for s in sentence_stream(_iter(tokens))]
    assert out == ["incomplete fragment"]


@pytest.mark.asyncio
async def test_handles_empty_stream():
    out = [s async for s in sentence_stream(_iter([]))]
    assert out == []
