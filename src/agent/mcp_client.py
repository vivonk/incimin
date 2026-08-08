"""Client for the incimin-sre MCP server.

The server speaks the *legacy* HTTP+SSE MCP transport, not Streamable HTTP:

    GET  /mcp/sse                     -> SSE stream; first `event: endpoint` carries the session path
    POST /mcp/messages?session_id=... -> JSON-RPC requests; responses come back on the SSE stream

Responses are correlated to requests by JSON-RPC id, which is what makes `call_tool_many` possible:
every request goes out before any response is awaited. Measured against the live server, fanning
`get_system_events` across 8 services took 3.7s that way versus ~25s *each* when issued serially.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

# Local, not a teammate's personal ngrok tunnel. The old default pointed at an
# external URL — safe only as long as someone was running it, and a landmine for
# anyone else: any caller that forgets INCIMIN_MCP_URL silently dials out to a
# tunnel it does not control. `src/production/main.py` serves this same server
# over SSE on the loopback address, which is what actually ships with this repo.
DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp/sse"

# The server's own tool calls are slow (15-30s cold, sub-second once its caches are warm), so these
# are deliberately generous — the failure we care about is a hung tunnel, not a slow query.
CONNECT_TIMEOUT = 30.0
CALL_TIMEOUT = 180.0


def mcp_url() -> str:
    """SSE endpoint. Env-overridable so a local server can replace ngrok without a code change."""
    return os.getenv("INCIMIN_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL


@dataclass
class ToolResult:
    """Outcome of one tool call. Errors are returned, not raised, so one failed component in a
    fanout cannot abort an entire diagnosis."""

    ok: bool
    data: Any = None
    error: str | None = None

    def unwrap(self, default: Any) -> Any:
        return self.data if self.ok else default


class MCPSession:
    """One MCP session over HTTP+SSE. Use as a context manager."""

    def __init__(self, url: str | None = None):
        self._url = url or mcp_url()
        self._base = self._url.split("/mcp/sse")[0]
        self._responses: queue.Queue[dict] = queue.Queue()
        self._endpoint: str | None = None
        self._stream = None
        self._reader: threading.Thread | None = None
        self._post_lock = threading.Lock()
        self._id_lock = threading.Lock()
        self._next_id = 0
        self._collected: dict[int, dict] = {}
        self._stop = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> "MCPSession":
        self._reader = threading.Thread(target=self._read_stream, daemon=True)
        self._reader.start()

        deadline = time.time() + CONNECT_TIMEOUT
        while self._endpoint is None and time.time() < deadline:
            if self._stop.is_set():
                raise ConnectionError(f"MCP stream closed before handshake: {self._url}")
            time.sleep(0.05)
        if self._endpoint is None:
            raise TimeoutError(f"No MCP endpoint event within {CONNECT_TIMEOUT}s from {self._url}")

        init_id = self._send(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "incimin-sre-agent", "version": "1"},
            },
        )
        self._await_ids({init_id}, CONNECT_TIMEOUT)
        self._notify("notifications/initialized")
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass

    def _read_stream(self) -> None:
        """Consume the SSE stream, routing `endpoint` to the session URL and everything else to the
        response queue."""
        try:
            req = urllib.request.Request(self._url, headers={"Accept": "text/event-stream"})
            self._stream = urllib.request.urlopen(req, timeout=CALL_TIMEOUT + CONNECT_TIMEOUT)
            event = None
            for raw in self._stream:
                if self._stop.is_set():
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    payload = line[5:].strip()
                    if event == "endpoint":
                        self._endpoint = payload
                    else:
                        try:
                            self._responses.put(json.loads(payload))
                        except json.JSONDecodeError:
                            pass
                elif line == "":
                    event = None
        except Exception:
            # Stream death is surfaced via handshake/call timeouts rather than crashing this thread.
            pass
        finally:
            self._stop.set()

    # -- JSON-RPC ----------------------------------------------------------

    def _allocate_id(self) -> int:
        with self._id_lock:
            self._next_id += 1
            return self._next_id

    def _post(self, message: dict) -> None:
        body = json.dumps(message).encode()
        req = urllib.request.Request(
            self._base + self._endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        # The server accepts one POST at a time; serialising the write is enough to keep calls
        # concurrent, since the slow part is the response arriving on the SSE stream.
        with self._post_lock:
            urllib.request.urlopen(req, timeout=CALL_TIMEOUT).read()

    def _send(self, method: str, params: dict | None = None) -> int:
        msg_id = self._allocate_id()
        self._post({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})
        return msg_id

    def _notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def _await_ids(self, wanted: set[int], timeout: float) -> dict[int, dict]:
        """Block until every id in `wanted` has been seen, or the deadline passes."""
        deadline = time.time() + timeout
        found = {i: self._collected.pop(i) for i in list(wanted) if i in self._collected}
        outstanding = wanted - set(found)
        while outstanding and time.time() < deadline:
            try:
                message = self._responses.get(timeout=0.5)
            except queue.Empty:
                if self._stop.is_set():
                    break
                continue
            msg_id = message.get("id")
            if msg_id in outstanding:
                found[msg_id] = message
                outstanding.discard(msg_id)
            elif msg_id is not None:
                # A response for a call we are not currently awaiting; keep it for its own waiter.
                self._collected[msg_id] = message
        return found

    # -- tools -------------------------------------------------------------

    @staticmethod
    def _parse(message: dict | None) -> ToolResult:
        if message is None:
            return ToolResult(ok=False, error="timed out waiting for response")
        if "error" in message:
            return ToolResult(ok=False, error=str(message["error"]))
        result = message.get("result") or {}
        if result.get("isError"):
            return ToolResult(ok=False, error="tool reported isError")
        content = result.get("content") or []
        if not content:
            return ToolResult(ok=True, data=None)
        text = content[0].get("text", "")
        try:
            return ToolResult(ok=True, data=json.loads(text))
        except json.JSONDecodeError:
            return ToolResult(ok=True, data=text)

    def call_tool(self, name: str, args: dict, timeout: float = CALL_TIMEOUT) -> ToolResult:
        try:
            call_id = self._send("tools/call", {"name": name, "arguments": args})
        except (urllib.error.URLError, OSError) as exc:
            return ToolResult(ok=False, error=f"transport error: {exc}")
        return self._parse(self._await_ids({call_id}, timeout).get(call_id))

    def call_tool_many(
        self, calls: list[tuple[str, dict]], timeout: float = CALL_TIMEOUT
    ) -> list[ToolResult]:
        """Issue every call before awaiting any, then collect by id.

        Results are returned in the same order as `calls`. This is the fanout that makes
        per-component change-log lookups affordable.
        """
        if not calls:
            return []

        ids: list[int | None] = []
        errors: dict[int, str] = {}
        for index, (name, args) in enumerate(calls):
            try:
                ids.append(self._send("tools/call", {"name": name, "arguments": args}))
            except (urllib.error.URLError, OSError) as exc:
                ids.append(None)
                errors[index] = f"transport error: {exc}"

        wanted = {i for i in ids if i is not None}
        received = self._await_ids(wanted, timeout)

        out: list[ToolResult] = []
        for index, call_id in enumerate(ids):
            if call_id is None:
                out.append(ToolResult(ok=False, error=errors[index]))
            else:
                out.append(self._parse(received.get(call_id)))
        return out


# -- convenience wrappers --------------------------------------------------


def get_service_topology(session: MCPSession, service: str, max_depth: int = 1) -> ToolResult:
    return session.call_tool(
        "get_service_topology", {"service_name": service, "max_depth": max_depth}
    )


def get_system_events_many(
    session: MCPSession, services: list[str], start_time: str, end_time: str
) -> dict[str, ToolResult]:
    """Change logs for many services at once. Keyed by service name."""
    calls = [
        ("get_system_events", {"service_name": s, "start_time": start_time, "end_time": end_time})
        for s in services
    ]
    return dict(zip(services, session.call_tool_many(calls)))
