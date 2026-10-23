"""JSON protocol for Flipper <-> Host Bridge communication."""

import json
import time
import uuid

def make_id() -> str:
    return uuid.uuid4().hex[:8]


def encode(msg_type: str, data: dict | None = None) -> bytes:
    msg = {
        "v": 1,
        "t": msg_type,
        "d": data or {},
    }
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


def decode(line: bytes) -> dict | None:
    msgs = decode_all(line)
    return msgs[0] if msgs else None


def decode_all(line: bytes) -> list[dict]:
    """Parse one or more JSON protocol messages from a serial line."""
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return []

    out: list[dict] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        if text[idx] != "{":
            next_brace = text.find("{", idx)
            if next_brace < 0:
                break
            idx = next_brace
        try:
            msg, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break
        if isinstance(msg, dict) and "t" in msg:
            out.append(msg)
        idx = end
    return out


def notify_msg(sound: str, vibro: bool = True, text: str = "", subtext: str = "") -> bytes:
    d: dict = {"sound": sound, "vibro": vibro, "text": text}
    if subtext:
        d["sub"] = subtext[:21]
    return encode("notify", d)


def state_msg(claude_connected: bool = False, host: str = "cursor") -> bytes:
    return encode("state", {"claude": claude_connected, "host": host})


def status_msg(line1: str, line2: str = "") -> bytes:
    d: dict = {"line1": line1[:21]}
    if line2:
        d["line2"] = line2[:21]
    return encode("status", d)


def ping_msg(rssi: int | None = None) -> bytes:
    d: dict[str, int] = {}
    if rssi is not None:
        d["rssi"] = int(rssi)
    return encode("ping", d)


def menu_msg(items: list[str]) -> bytes:
    return encode("menu", {"items": "|".join(items)})


def perm_msg(tool: str, detail: str = "") -> bytes:
    d: dict = {"tool": tool[:21]}
    if detail:
        d["detail"] = detail[:21]
    return encode("perm", d)


def usage_msg(
    context_pct: int | None = None,
    session_pct: int | None = None,
    compact_level: int | None = None,
) -> bytes:
    d: dict[str, int] = {}
    if context_pct is not None:
        d["ctx"] = max(0, min(100, int(context_pct)))
    if session_pct is not None:
        d["sess"] = max(0, min(100, int(session_pct)))
    if compact_level is not None:
        d["clvl"] = max(0, min(3, int(compact_level)))
    return encode("usage", d)
