"""Tests for the SSE encoder inside app/main.py's events() endpoint.

events() returns a StreamingResponse whose body_iterator is the encoder under
test. We drive it directly (no network, no ASGI server) by:
  - creating a real Session in the in-memory store,
  - calling events() with a fake request that never disconnects,
  - publishing events onto the session's queue,
  - reading exactly the frames we published from the response body_iterator.

We read only as many frames as we publish, so the generator never blocks on its
15s keepalive timeout.
"""

import asyncio

from app import main
from app.wizard import state


class _FakeRequest:
    """Minimal stand-in: events() only calls request.is_disconnected()."""

    async def is_disconnected(self) -> bool:
        return False


async def _frames_for(events_to_publish):
    """Publish a list of (event, data) (data may be a raw object to inject a
    non-string payload directly onto the queue) and return the encoded frames."""
    s = state.create()
    resp = await main.events(_FakeRequest(), s.id)
    it = resp.body_iterator
    try:
        # The subscriber queue now exists; enqueue the test events.
        for event, data in events_to_publish:
            if isinstance(data, str):
                s.publish(event, data)
            else:
                # Inject a non-string payload directly to exercise the
                # json.dumps branch in the encoder.
                s.subscribers[0].put_nowait({"event": event, "data": data})
        frames = []
        for _ in range(len(events_to_publish)):
            frames.append(await it.__anext__())
        return frames
    finally:
        await it.aclose()


def _one(event, data):
    return asyncio.run(_frames_for([(event, data)]))[0]


def test_event_name_and_single_line_payload():
    frame = _one("progress", "hello world")
    assert frame == "event: progress\ndata: hello world\n\n"


def test_multiline_payload_one_data_line_per_line():
    frame = _one("progress", "line1\nline2\nline3")
    # SSE requires one `data:` field per physical line.
    assert frame == "event: progress\ndata: line1\ndata: line2\ndata: line3\n\n"
    assert frame.count("data: ") == 3


def test_error_channel_is_html_escaped():
    frame = _one("error", "<script>alert('xss')</script>")
    assert "<script>" not in frame
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in frame
    assert frame.startswith("event: error\n")


def test_trusted_channel_is_not_escaped():
    # progress carries server-built trusted HTML and must pass through verbatim.
    frame = _one("progress", '<span class="spinner"></span> Working…')
    assert '<span class="spinner"></span> Working…' in frame
    assert "&lt;" not in frame


def test_party_msg_channel_not_escaped():
    frame = _one("party_msg", "<div class='bubble'>hi</div>")
    assert "<div class='bubble'>hi</div>" in frame


def test_empty_payload_produces_single_empty_data_line():
    frame = _one("progress", "")
    assert frame == "event: progress\ndata: \n\n"


def test_multiline_error_is_escaped_then_split():
    frame = _one("error", "<b>bad</b>\nsecond line")
    # Escaped first, then split into per-line data: fields.
    assert "&lt;b&gt;bad&lt;/b&gt;" in frame
    assert "<b>" not in frame
    assert frame.count("data: ") == 2


def test_non_string_payload_is_json_encoded():
    frame = _one("custom", {"k": "v", "n": 1})
    assert frame.startswith("event: custom\n")
    assert 'data: {"k": "v", "n": 1}\n' in frame


def test_multiple_events_stream_in_order():
    frames = asyncio.run(
        _frames_for([("progress", "first"), ("progress", "second"), ("error", "third")])
    )
    assert frames[0] == "event: progress\ndata: first\n\n"
    assert frames[1] == "event: progress\ndata: second\n\n"
    assert frames[2].startswith("event: error\ndata: third\n\n")
