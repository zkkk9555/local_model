#!/usr/bin/env python3
"""mcp_server.py - MCP stdio server for the NInfer 27B kv-stream package.

TRANSPORT
  python mcp_server.py --mcp
  One JSON-RPC 2.0 message per line on stdin/stdout (NDJSON, UTF-8).
  Each request line is capped at 1 MiB: a larger line is drained, answered with
  JSON-RPC error -32600 and the loop continues.  stdout carries protocol
  messages only; all diagnostics go to stderr.

TOOLS (exactly five, all prefixed local_llm.)
  local_llm.status()                 engine/gateway liveness + VRAM + numbers from run\\pid.json
  local_llm.profiles()               profile tiers read from <package>\\profiles.json
  local_llm.chat(messages, ...)      POST :8081 (gateway), fall back to :8080 (engine)
  local_llm.ask_long(material, ...)  one-shot long material; refuses when material > pool
  local_llm.plan_config(vram_gib, ...)  KV-pool arithmetic, same constants as profiles.json

NO LIFECYCLE TOOLS
  This file does NOT register start/stop (or any process control).  The flag
  --allow-lifecycle is accepted for forward compatibility but is a NO-OP: this
  server never starts, stops or kills the engine or the gateway, whatever flag
  is passed on the command line.  Lifecycle belongs to the package launcher.

DEPENDENCIES
  Python standard library only.  Source is ASCII; no third-party imports.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.path.join(ROOT, "run")
PID_JSON = os.path.join(RUN_DIR, "pid.json")
PROFILES_JSON = os.path.join(ROOT, "profiles.json")
# profiles.json is the documented location; the other two are tolerant fallbacks
# for launcher layouts that keep the file under a subdirectory.
PROFILES_CANDIDATES = [
    PROFILES_JSON,
    os.path.join(ROOT, "profiles", "default.json"),
    os.path.join(ROOT, "launcher", "profiles", "default.json"),
]

ENGINE_BASE = "http://127.0.0.1:8080"
GATEWAY_BASE = "http://127.0.0.1:8081"

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "ninfer-27b-kv-stream-mcp"
SERVER_VERSION = "1.0.0"

MAX_LINE_BYTES = 1 << 20          # 1 MiB per protocol line
MAX_MATERIAL_BYTES = 200 * 1024    # ask_long hard cap on material
DEFAULT_POOL_TOKENS = 16384        # only used when pid.json has no pool_tokens
HTTP_PROBE_TIMEOUT = 3.0
CHAT_TIMEOUT = 300.0

# ---------------------------------------------------------------------------
# plan_config arithmetic (same numbers as profiles.json / kv_plan model)
#   engine(dtype) = engine_fixed(quant) + pages * slope(dtype)
#   red line      = vram_gib * 1024 - reserve - 300        (300 MiB desktop)
#   reserve       = 400 MiB on <= 8 GiB cards, else 500 MiB
# ---------------------------------------------------------------------------
PLAN_ENGINE_FIXED = {"ptq1": 7254.0, "ptq2": 8463.0}
PLAN_SLOPE = {"rk2v4-e8": 0.8357, "k8v4": 1.602}
PLAN_FULL_PREFERENCE = ["k8v4", "rk2v4-e8"]   # better quality first when it fits
PLAN_RING_PREFERENCE = ["rk2v4-e8", "k8v4"]   # cheaper slope first when pooling
PLAN_PAGE_TOKENS = 64
PLAN_MIN_POOL_PAGES = 8
PLAN_MAX_CTX = 262144


class ToolError(Exception):
    """Error that maps onto a JSON-RPC error object instead of a tool result."""

    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _read_json(path):
    """Return (value, error_string).  Missing file -> (None, 'missing')."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "missing: %s" % path
    except Exception as exc:  # noqa: BLE001 - report, never crash the server
        return None, "%s: %s" % (type(exc).__name__, exc)


def _pid_alive(pid):
    """True if pid names a live process.  Never terminates anything."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, 0, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) == 0:
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _http_json(url, payload=None, timeout=HTTP_PROBE_TIMEOUT):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data is not None else "GET"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return response.status, json.loads(body.decode("utf-8", "replace"))


def _gpu_used_mib():
    """VRAM used in MiB via nvidia-smi, or None when the probe is unavailable."""
    try:
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=4,
            **kwargs
        )
        if proc.returncode != 0:
            return None
        first = (proc.stdout or "").strip().splitlines()
        if not first:
            return None
        token = first[0].strip().split()[0]
        return int(float(token))
    except Exception:  # noqa: BLE001 - nvidia-smi absent/slow is not an error
        return None


def _pick(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping:
            value = mapping[key]
            if value not in (None, ""):
                return value
    return None


def _scan_pid_doc(doc):
    """Best-effort flat view of run\\pid.json across plausible launcher layouts."""
    flat = {}
    if isinstance(doc, dict):
        for key, value in doc.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat.setdefault(sub_key, sub_value)
                flat.setdefault(key, value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        for sub_key, sub_value in item.items():
                            flat.setdefault(sub_key, sub_value)
            else:
                flat.setdefault(key, value)
    return flat


def _load_pid_flat():
    doc, error = _read_json(PID_JSON)
    return _scan_pid_doc(doc), error


# ---------------------------------------------------------------------------
# tool: local_llm.status
# ---------------------------------------------------------------------------
def tool_status():
    flat, pid_error = _load_pid_flat()

    pid_engine = _pick(flat, "pid_engine", "engine_pid")
    pid_gateway = _pick(flat, "pid_gateway", "gateway_pid")

    models_ok = False
    models = []
    engine_http_error = None
    try:
        _, body = _http_json(ENGINE_BASE + "/v1/models", timeout=HTTP_PROBE_TIMEOUT)
        models = [item.get("id") for item in (body.get("data") or []) if isinstance(item, dict)]
        models_ok = True
    except Exception as exc:  # noqa: BLE001 - engine down is a normal state
        engine_http_error = "%s: %s" % (type(exc).__name__, exc)

    engine_alive = _pid_alive(pid_engine)
    gateway_alive = _pid_alive(pid_gateway)
    file_last_error = _pick(flat, "last_error", "error", "error_message")
    last_error = file_last_error
    if not last_error and not models_ok and engine_http_error:
        last_error = engine_http_error

    return {
        "running": bool(models_ok or engine_alive or gateway_alive),
        "arch": _pick(flat, "arch", "model_arch", "device_arch"),
        "pool_tokens": _pick(flat, "pool_tokens", "kv_capacity", "pool"),
        "engine_mib_est": _pick(flat, "engine_mib_est", "engine_pred", "engine_mib"),
        "gpu_used_mib": _gpu_used_mib(),
        "pid_engine": pid_engine,
        "pid_gateway": pid_gateway,
        "last_error": last_error or "",
        # evidence fields (not part of the required set, kept for diagnosis)
        "engine_http_ok": models_ok,
        "models": models,
        "pid_alive": {"engine": engine_alive, "gateway": gateway_alive},
        "pid_json": PID_JSON,
        "pid_json_error": pid_error,
    }


# ---------------------------------------------------------------------------
# tool: local_llm.profiles
# ---------------------------------------------------------------------------
PROFILE_FIELDS = ("pool", "dtype", "host_kv_mib", "mtp", "reserve", "engine_pred", "predicted")
PROFILE_ALIASES = {
    "pool": ("pool", "pool_tokens", "kv_capacity", "tokens"),
    "dtype": ("dtype", "kv_dtype"),
    "host_kv_mib": ("host_kv_mib", "host_kv", "host_mib"),
    "mtp": ("mtp", "mtp_enabled"),
    "reserve": ("reserve", "reserve_mib"),
    "engine_pred": ("engine_pred", "engine_mib", "engine"),
    "predicted": ("predicted", "predicted_ok", "ok"),
}


def _extract_profile(entry):
    """Normalise one profile entry to the seven documented fields plus passthrough."""
    result = {}
    for field in PROFILE_FIELDS:
        value = _pick(entry, *PROFILE_ALIASES[field])
        result[field] = value
    for key, value in entry.items():
        result.setdefault(key, value)
    return result


def _load_profiles_doc():
    errors = []
    for path in PROFILES_CANDIDATES:
        doc, error = _read_json(path)
        if doc is not None:
            return doc, path, None
        errors.append(error)
    return None, PROFILES_CANDIDATES[0], "; ".join(item for item in errors if item)


def tool_profiles():
    doc, source, error = _load_profiles_doc()
    if doc is None:
        return {"profiles": {}, "keys": [], "count": 0, "source": source, "error": error}

    tiers = None
    if isinstance(doc, dict):
        for key in ("profiles", "tiers", "levels", "presets"):
            candidate = doc.get(key)
            if isinstance(candidate, dict):
                tiers = candidate
                break
        if tiers is None:
            meta = ("schema", "version", "default", "default_profile", "note", "notes", "comment")
            plain = {
                key: value
                for key, value in doc.items()
                if isinstance(value, dict) and key.lower() not in meta
            }
            tiers = plain if plain else None
    if tiers is None:
        return {
            "profiles": {},
            "keys": [],
            "count": 0,
            "source": source,
            "error": "profiles.json has no profile map (expected {name: {...}} or {'profiles': {...}})",
        }

    profiles = {name: _extract_profile(entry) for name, entry in tiers.items()}
    default = None
    if isinstance(doc, dict):
        default = _pick(doc, "default", "default_profile")
    return {
        "profiles": profiles,
        "keys": list(profiles.keys()),
        "count": len(profiles),
        "default": default,
        "source": source,
    }


# ---------------------------------------------------------------------------
# tool: local_llm.chat
# ---------------------------------------------------------------------------
def _chat_once(base, messages, max_tokens, thinking):
    body = {"messages": messages, "max_tokens": int(max_tokens), "stream": False}
    if thinking:
        body["chat_template_kwargs"] = {"enable_thinking": True}
    status, reply = _http_json(base + "/v1/chat/completions", body, timeout=CHAT_TIMEOUT)
    if not isinstance(reply, dict):
        raise RuntimeError("non-object reply from %s" % base)
    if reply.get("error"):
        raise RuntimeError("engine error: %s" % json.dumps(reply.get("error"), ensure_ascii=True))
    choices = reply.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise RuntimeError("no choices in reply from %s" % base)
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if content is None:
        content = message.get("reasoning_content") or ""
    timings = reply.get("timings")
    if timings is None:
        usage = reply.get("usage") or {}
        timings = usage.get("timings") if isinstance(usage, dict) else None
    return {
        "content": content,
        "finish_reason": choice.get("finish_reason"),
        "usage": reply.get("usage"),
        "timings": timings or {},
        "http_status": status,
    }


def _chat_impl(messages, max_tokens=256, thinking=False):
    if not isinstance(messages, list) or not messages:
        raise ToolError(-32602, "messages must be a non-empty array")
    for index, item in enumerate(messages):
        if not isinstance(item, dict) or "role" not in item:
            raise ToolError(-32602, "messages[%d] must be an object with 'role'" % index)

    errors = []
    for base, via in ((GATEWAY_BASE, "gateway"), (ENGINE_BASE, "engine")):
        try:
            result = _chat_once(base, messages, max_tokens, thinking)
        except Exception as exc:  # noqa: BLE001 - try the next endpoint
            errors.append("%s(%s): %s: %s" % (via, base, type(exc).__name__, exc))
            continue
        result["via"] = via
        result["endpoint"] = base
        return result
    return {"content": "", "finish_reason": None, "usage": None, "timings": {},
            "via": None, "error": "no chat endpoint reachable", "attempts": errors}


def tool_chat(arguments):
    return _chat_impl(
        arguments.get("messages"),
        arguments.get("max_tokens", 256),
        bool(arguments.get("thinking", False)),
    )


# ---------------------------------------------------------------------------
# tool: local_llm.ask_long
# ---------------------------------------------------------------------------
MODE_PROMPTS = {
    "locate": "Answer only from the material. Quote the exact span that contains the answer. "
              "If the material does not contain it, answer NOT_FOUND.",
    "aggregate": "Aggregate across the whole material (counts, totals, comparisons). "
                 "Cite the spans you used. If the material is insufficient, say so.",
    "chat": "Answer the question using the material as context.",
}


def _current_pool_tokens():
    """Pool size and where it came from: (pool_tokens, source)."""
    flat, _ = _load_pid_flat()
    pool = _pick(flat, "pool_tokens", "kv_capacity", "pool")
    try:
        if pool is not None:
            return int(pool), "pid.json"
    except (TypeError, ValueError):
        pass
    doc, source, _error = _load_profiles_doc()
    if isinstance(doc, dict):
        tiers = doc.get("profiles") if isinstance(doc.get("profiles"), dict) else doc
        if isinstance(tiers, dict):
            default = _pick(doc, "default", "default_profile")
            entry = tiers.get(default) if isinstance(default, str) else None
            if not isinstance(entry, dict):
                for value in tiers.values():
                    if isinstance(value, dict):
                        entry = value
                        break
            if isinstance(entry, dict):
                value = _pick(entry, "pool", "pool_tokens", "kv_capacity")
                try:
                    if value is not None:
                        return int(value), source
                except (TypeError, ValueError):
                    pass
    return DEFAULT_POOL_TOKENS, "default_assumed"


def tool_ask_long(arguments):
    material = arguments.get("material")
    question = arguments.get("question")
    mode = arguments.get("mode", "locate")
    if not isinstance(material, str):
        raise ToolError(-32602, "material must be a string")
    if not isinstance(question, str) or not question.strip():
        raise ToolError(-32602, "question must be a non-empty string")
    if mode not in MODE_PROMPTS:
        raise ToolError(-32602, "mode must be one of locate | aggregate | chat")

    size = len(material.encode("utf-8", "replace"))
    if size > MAX_MATERIAL_BYTES:
        raise ToolError(
            -32000,
            "material too large: %d bytes > %d bytes limit; refusing (this tool does not chunk)"
            % (size, MAX_MATERIAL_BYTES),
        )

    pool, pool_source = _current_pool_tokens()
    estimated = len(material) // 2  # rough token estimate, documented in the spec
    if estimated > pool:
        return {
            "answer": "",
            "fallback_level": "refused_too_long",
            "trusted": False,
            "note": "material exceeds the pool; chunking is required and this tool does not chunk",
            "estimated_tokens": estimated,
            "pool_tokens": pool,
            "pool_source": pool_source,
            "material_bytes": size,
            "mode": mode,
        }

    messages = [
        {"role": "system", "content": MODE_PROMPTS[mode]},
        {"role": "user", "content": material + "\n\n---\nQUESTION:\n" + question},
    ]
    reply = _chat_impl(messages, arguments.get("max_tokens", 256), False)
    if reply.get("error"):
        return {
            "answer": "",
            "fallback_level": "error",
            "trusted": False,
            "note": reply["error"],
            "attempts": reply.get("attempts", []),
            "estimated_tokens": estimated,
            "pool_tokens": pool,
        }
    return {
        "answer": reply.get("content") or "",
        "fallback_level": "L0",
        "segments": 1,
        "trusted": True,
        "estimated_tokens": estimated,
        "pool_tokens": pool,
        "pool_source": pool_source,
        "material_bytes": size,
        "mode": mode,
        "via": reply.get("via"),
        "finish_reason": reply.get("finish_reason"),
        "usage": reply.get("usage"),
        "timings": reply.get("timings"),
    }


# ---------------------------------------------------------------------------
# tool: local_llm.plan_config
# ---------------------------------------------------------------------------
def tool_plan_config(arguments):
    try:
        vram_gib = float(arguments["vram_gib"])
    except (KeyError, TypeError, ValueError):
        raise ToolError(-32602, "vram_gib is required and must be a number")
    quant = str(arguments.get("quant", "ptq1")).lower()
    if quant not in PLAN_ENGINE_FIXED:
        raise ToolError(-32602, "quant must be ptq1 or ptq2")
    try:
        context = int(arguments.get("ctx", PLAN_MAX_CTX))
    except (TypeError, ValueError):
        raise ToolError(-32602, "ctx must be an integer")
    if context <= 0:
        raise ToolError(-32602, "ctx must be positive")
    if context > PLAN_MAX_CTX:
        raise ToolError(-32602, "ctx %d exceeds the model limit %d" % (context, PLAN_MAX_CTX))

    reserve = 400.0 if vram_gib <= 8.0 else 500.0
    desktop = 300.0
    redline = vram_gib * 1024.0 - reserve - desktop
    engine_fixed = PLAN_ENGINE_FIXED[quant]
    pages_needed = (context + PLAN_PAGE_TOKENS - 1) // PLAN_PAGE_TOKENS

    dtype = None
    mode = None
    pool_pages = 0
    for candidate in PLAN_FULL_PREFERENCE:
        slope = PLAN_SLOPE[candidate]
        if engine_fixed + slope * pages_needed <= redline:
            dtype, mode, pool_pages = candidate, "full", pages_needed
            break

    if dtype is None:
        best = None
        avail = redline - engine_fixed
        for candidate in PLAN_RING_PREFERENCE:
            slope = PLAN_SLOPE[candidate]
            pages = int(avail // slope) if avail > 0 else 0
            pages = min(pages, pages_needed)
            if pages < PLAN_MIN_POOL_PAGES:
                continue
            if best is None or pages > best[1]:
                best = (candidate, pages)
        if best is not None:
            dtype, pool_pages = best
            mode = "ring"

    base = {
        "vram_gib": vram_gib,
        "quant": quant,
        "ctx": context,
        "reserve_mib": reserve,
        "desktop_mib": desktop,
        "redline_mib": round(redline, 1),
        "engine_fixed_mib": engine_fixed,
    }

    if dtype is None:
        min_vram = int(math.ceil((engine_fixed + reserve + desktop) / 1024.0))
        small_ctx = PLAN_MAX_CTX
        avail = redline - engine_fixed
        for candidate in PLAN_RING_PREFERENCE:
            pages = int(avail // PLAN_SLOPE[candidate]) if avail > 0 else 0
            small_ctx = min(small_ctx, pages * PLAN_PAGE_TOKENS)
        note = (
            "infeasible: engine_fixed %.0f MiB + desktop %.0f MiB + reserve %.0f MiB needs at "
            "least %d GiB of VRAM; at %.1f GiB the red line is %.0f MiB and the KV budget is "
            "%.0f MiB (below the %d-page floor)"
            % (engine_fixed, desktop, reserve, min_vram, vram_gib, redline, max(avail, 0.0),
               PLAN_MIN_POOL_PAGES)
        )
        suggestion = (
            "use a card with >= %d GiB, or reduce ctx (largest pool at this VRAM fits about "
            "%d tokens), or use quant=ptq2 only if the card is bigger"
            % (min_vram, max(small_ctx, 0))
        )
        result = dict(base)
        result.update({
            "dtype": None,
            "mode": None,
            "pool_tokens": 0,
            "pool_pages": 0,
            "host_kv_mib": 0,
            "engine_pred": None,
            "margin_mib": round(redline - engine_fixed, 1),
            "feasible": False,
            "note": note,
            "suggestion": suggestion,
        })
        return result

    slope = PLAN_SLOPE[dtype]
    engine_pred = round(engine_fixed + slope * pool_pages, 1)
    pool_tokens = pool_pages * PLAN_PAGE_TOKENS
    if mode == "full":
        host_kv_mib = 0
    else:
        host_kv_mib = int(math.ceil((pages_needed - pool_pages) * slope))
    margin = round(redline - engine_pred, 1)

    result = dict(base)
    result.update({
        "dtype": dtype,
        "mode": mode,
        "pool_tokens": pool_tokens,
        "pool_pages": pool_pages,
        "host_kv_mib": host_kv_mib,
        "engine_pred": engine_pred,
        "margin_mib": margin,
        "feasible": bool(engine_pred <= redline and pool_pages >= PLAN_MIN_POOL_PAGES),
        "slope_mib_per_page": slope,
    })
    if mode == "ring":
        result["note"] = (
            "context %d does not fit fully resident: pool %d tokens, remainder %d MiB on host"
            % (context, pool_tokens, host_kv_mib)
        )
    return result


# ---------------------------------------------------------------------------
# MCP tool table
# ---------------------------------------------------------------------------
EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}

TOOLS = [
    {
        "name": "local_llm.status",
        "description": (
            "Liveness and numbers: reads run/pid.json, probes GET http://127.0.0.1:8080/v1/models "
            "(3 s timeout) and nvidia-smi. Returns running, arch, pool_tokens, engine_mib_est, "
            "gpu_used_mib, pid_engine, pid_gateway, last_error."
        ),
        "inputSchema": EMPTY_SCHEMA,
    },
    {
        "name": "local_llm.profiles",
        "description": (
            "Profile tiers from the package profiles.json: key names and, per tier, "
            "pool, dtype, host_kv_mib, mtp, reserve, engine_pred, predicted."
        ),
        "inputSchema": EMPTY_SCHEMA,
    },
    {
        "name": "local_llm.chat",
        "description": (
            "Chat through the gateway 127.0.0.1:8081/v1/chat/completions, falling back to the "
            "engine on 127.0.0.1:8080 (result then carries via='engine'). Returns content, "
            "finish_reason, usage, timings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "description": "OpenAI-style messages, e.g. [{role: 'user', content: '...'}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                        "additionalProperties": True,
                    },
                },
                "max_tokens": {"type": "integer", "default": 256, "minimum": 1},
                "thinking": {"type": "boolean", "default": False},
            },
            "required": ["messages"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_llm.ask_long",
        "description": (
            "One-shot long material question. If the estimated token count (len(material)//2) "
            "exceeds the current pool it REFUSES with fallback_level='refused_too_long' "
            "(no chunking is faked). Material over 200 KB is rejected as an error. Otherwise "
            "calls chat and returns answer, fallback_level='L0', segments=1, trusted=true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "material": {"type": "string", "description": "Material text to read"},
                "question": {"type": "string", "description": "Question about the material"},
                "mode": {
                    "type": "string",
                    "enum": ["locate", "aggregate", "chat"],
                    "default": "locate",
                },
                "max_tokens": {"type": "integer", "default": 256, "minimum": 1},
            },
            "required": ["material", "question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "local_llm.plan_config",
        "description": (
            "KV-pool arithmetic. engine_fixed 7254 MiB (ptq1) / 8463 MiB (ptq2); slope "
            "rk2v4-e8 0.8357 / k8v4 1.602 MiB per 64-token page; reserve 400 MiB (<=8 GiB) or "
            "500 MiB; red line = vram_gib*1024 - reserve - 300. Returns dtype, pool_tokens, "
            "host_kv_mib, engine_pred, margin_mib, feasible (plus suggestion when infeasible)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vram_gib": {"type": "number", "description": "Card VRAM in GiB, e.g. 8"},
                "quant": {"type": "string", "enum": ["ptq1", "ptq2"], "default": "ptq1"},
                "ctx": {"type": "integer", "default": 262144, "minimum": 1,
                        "maximum": PLAN_MAX_CTX},
            },
            "required": ["vram_gib"],
            "additionalProperties": False,
        },
    },
]

TOOL_HANDLERS = {
    "local_llm.status": lambda arguments: tool_status(),
    "local_llm.profiles": lambda arguments: tool_profiles(),
    "local_llm.chat": tool_chat,
    "local_llm.ask_long": tool_ask_long,
    "local_llm.plan_config": tool_plan_config,
}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------
def _error_response(request_id, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_result(payload, is_error=False):
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=True, indent=2)}],
        "isError": bool(is_error),
    }


def _dispatch_call(params):
    if not isinstance(params, dict):
        raise ToolError(-32602, "tools/call requires an object params")
    name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(name, str):
        raise ToolError(-32602, "tools/call requires params.name")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolError(-32602, "tools/call params.arguments must be an object")
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ToolError(-32602, "unknown tool: %s" % name)
    try:
        payload = handler(arguments)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface the failure, never swallow it
        raise ToolError(-32603, "%s: %s" % (type(exc).__name__, exc))
    if isinstance(payload, dict) and payload.get("error") and name == "local_llm.chat":
        return _tool_result(payload, is_error=True)
    return _tool_result(payload)


def _handle_message(message):
    """Return a response dict, or None when the message is a notification."""
    if not isinstance(message, dict):
        return _error_response(None, -32600, "request must be a JSON object")
    request_id = message.get("id")
    is_notification = "id" not in message
    method = message.get("method")

    if method == "notifications/initialized" or is_notification:
        return None
    if not isinstance(method, str):
        return _error_response(request_id, -32600, "missing method")

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = _dispatch_call(message.get("params"))
        else:
            return _error_response(request_id, -32601, "method not found: %s" % method)
    except ToolError as exc:
        return _error_response(request_id, exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001
        return _error_response(request_id, -32603, "internal error: %s: %s"
                               % (type(exc).__name__, exc))

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


OVERSIZE = object()


def _read_line(stream):
    """Read one line capped at MAX_LINE_BYTES; return OVERSIZE for a too-long line."""
    line = stream.readline(MAX_LINE_BYTES + 2)
    if not line:
        return None
    if len(line) > MAX_LINE_BYTES + 1 or (len(line) > MAX_LINE_BYTES and not line.endswith(b"\n")):
        while True:
            chunk = stream.readline(MAX_LINE_BYTES + 2)
            if not chunk or chunk.endswith(b"\n"):
                break
        return OVERSIZE
    return line


def serve_stdio():
    stdin = sys.stdin.buffer
    stdout = sys.stdout
    while True:
        raw = _read_line(stdin)
        if raw is None:
            return 0
        if raw is OVERSIZE:
            stdout.write(json.dumps(_error_response(
                None, -32600, "message exceeds the 1 MiB line limit"), ensure_ascii=True) + "\n")
            stdout.flush()
            continue
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except ValueError as exc:
            stdout.write(json.dumps(
                _error_response(None, -32700, "parse error: %s" % exc), ensure_ascii=True) + "\n")
            stdout.flush()
            continue
        if isinstance(message, list):
            response = _error_response(None, -32600, "batch requests are not supported")
        else:
            response = _handle_message(message)
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
        stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="MCP stdio server (5 local_llm.* tools) for the NInfer kv-stream package.")
    parser.add_argument("--mcp", action="store_true",
                        help="serve MCP over stdin/stdout (NDJSON JSON-RPC 2.0)")
    parser.add_argument("--allow-lifecycle", action="store_true",
                        help="accepted for compatibility; NOT implemented here (no-op)")
    arguments = parser.parse_args(argv)
    if arguments.allow_lifecycle:
        sys.stderr.write("[mcp] note: --allow-lifecycle is a no-op; this server registers no "
                         "start/stop tools\n")
    if not arguments.mcp:
        sys.stderr.write("usage: python mcp_server.py --mcp\n")
        return 2
    return serve_stdio()


if __name__ == "__main__":
    sys.exit(main())
