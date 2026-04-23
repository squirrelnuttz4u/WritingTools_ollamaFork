"""Flask proxy from Office.js Outlook add-in to the internal Ollama server."""
import json
import logging
import os
import time
from typing import Any, Dict, Generator, Optional

import requests
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama.internal:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.4"))
API_KEY = os.environ.get("API_KEY", "").strip()
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "120"))
TLS_CERT = os.environ.get("TLS_CERT", "").strip()
TLS_KEY = os.environ.get("TLS_KEY", "").strip()
PORT = int(os.environ.get("PORT", "5000"))
HOST = os.environ.get("HOST", "0.0.0.0")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
log = logging.getLogger("ollama-proxy")

app = Flask(__name__)
CORS(
    app,
    origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else "*",
    supports_credentials=False,
    allow_headers=["Authorization", "Content-Type"],
    methods=["GET", "POST", "OPTIONS"],
)


TONE_INSTRUCTIONS: Dict[str, str] = {
    "professional": "Rewrite in a polished, professional business tone, keeping it clear and neutral.",
    "friendly": "Rewrite in a warm, friendly tone while staying respectful and professional.",
    "concise": "Rewrite to be significantly shorter and more concise without losing meaning.",
    "formal": "Rewrite in a highly formal tone suitable for executive or external communication.",
    "assertive": "Rewrite in a confident, assertive tone that states expectations and next steps clearly.",
    "apologetic": "Rewrite with a sincere, apologetic tone that takes ownership and offers a path forward.",
    "grammar": "Fix grammar, spelling, and punctuation only. Preserve the original wording, voice, and meaning.",
}

REWRITE_SYSTEM = (
    "You are an assistant that rewrites email drafts. "
    "Output ONLY the rewritten email body with no preamble, no commentary, no surrounding quotes, "
    "and no markdown fences. "
    "Preserve the original language of the input (do not translate). "
    "Preserve any signature block, greetings, and factual content such as names, dates, numbers, and links. "
    "Do not invent recipients, attachments, or commitments that are not present in the input."
)

SUMMARIZE_SYSTEM = (
    "You are an assistant that summarizes email threads for a busy reader. "
    "Return plain text (no markdown fences) structured as:\n"
    "TL;DR: one sentence.\n"
    "Key points:\n- bullet\n- bullet\n"
    "Action items:\n- owner: action (due date if present)\n"
    "If there are no action items, write 'Action items: none'. "
    "Preserve the original language of the input."
)


def _auth_ok() -> bool:
    if not API_KEY:
        return True
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    return header.split(None, 1)[1].strip() == API_KEY


@app.before_request
def _enforce_auth():
    if request.method == "OPTIONS":
        return None
    if request.path == "/health":
        return None
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    return None


def _ollama_chat(
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    stream: bool = False,
):
    """Call Ollama's /api/chat endpoint.

    When stream=True returns a generator of parsed JSON dicts; otherwise returns the parsed response dict.
    """
    payload: Dict[str, Any] = {
        "model": model or OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": bool(stream),
        "options": {
            "temperature": LLM_TEMPERATURE if temperature is None else float(temperature),
            "num_predict": LLM_MAX_TOKENS if max_tokens is None else int(max_tokens),
        },
    }
    url = f"{OLLAMA_URL}/api/chat"

    if not stream:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def _gen() -> Generator[Dict[str, Any], None, None]:
        with requests.post(url, json=payload, stream=True, timeout=REQUEST_TIMEOUT) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    log.warning("could not parse ollama stream line: %r", line)
                    continue

    return _gen()


@app.route("/health", methods=["GET"])
def health():
    start = time.time()
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        latency_ms = int((time.time() - start) * 1000)
        return jsonify({
            "status": "ok",
            "ollama_url": OLLAMA_URL,
            "ollama_reachable": True,
            "default_model": OLLAMA_MODEL,
            "latency_ms": latency_ms,
        })
    except requests.RequestException as e:
        latency_ms = int((time.time() - start) * 1000)
        return jsonify({
            "status": "degraded",
            "ollama_url": OLLAMA_URL,
            "ollama_reachable": False,
            "default_model": OLLAMA_MODEL,
            "latency_ms": latency_ms,
            "error": str(e),
        }), 503


@app.route("/models", methods=["GET"])
def models():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        r.raise_for_status()
        data = r.json()
        names = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return jsonify({"models": names, "default": OLLAMA_MODEL})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


@app.route("/generate", methods=["POST"])
def generate():
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    system = body.get("system") or "You are a helpful assistant."
    model = body.get("model")
    try:
        data = _ollama_chat(
            system=system,
            user=prompt,
            model=model,
            temperature=body.get("temperature"),
            max_tokens=body.get("max_tokens"),
            stream=False,
        )
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502
    text = ((data or {}).get("message") or {}).get("content", "")
    return jsonify({"text": text, "model": (data or {}).get("model", model or OLLAMA_MODEL)})


@app.route("/generate_sse", methods=["POST"])
def generate_sse():
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    system = body.get("system") or "You are a helpful assistant."
    model = body.get("model")
    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")

    def _sse():
        try:
            chunks = _ollama_chat(
                system=system,
                user=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in chunks:
                delta = ((chunk or {}).get("message") or {}).get("content", "")
                if delta:
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
                if chunk.get("done"):
                    break
            yield f"data: {json.dumps({'done': True})}\n\n"
        except requests.RequestException as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(_sse()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/rewrite", methods=["POST"])
def rewrite():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    tone = (body.get("tone") or "professional").lower()
    extra = (body.get("instructions") or "").strip()
    model = body.get("model")
    if not text:
        return jsonify({"error": "text is required"}), 400
    if tone not in TONE_INSTRUCTIONS:
        return jsonify({"error": f"unknown tone '{tone}'"}), 400

    tone_instruction = TONE_INSTRUCTIONS[tone]
    user_msg = f"{tone_instruction}\n"
    if extra:
        user_msg += f"Additional instructions from the user: {extra}\n"
    user_msg += "\n---\nEMAIL DRAFT:\n" + text

    try:
        data = _ollama_chat(
            system=REWRITE_SYSTEM,
            user=user_msg,
            model=model,
            stream=False,
        )
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    rewritten = ((data or {}).get("message") or {}).get("content", "").strip()
    return jsonify({
        "text": rewritten,
        "tone": tone,
        "model": (data or {}).get("model", model or OLLAMA_MODEL),
    })


@app.route("/summarize", methods=["POST"])
def summarize():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    model = body.get("model")
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        data = _ollama_chat(
            system=SUMMARIZE_SYSTEM,
            user="Summarize the following email or thread:\n\n" + text,
            model=model,
            stream=False,
        )
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502

    summary = ((data or {}).get("message") or {}).get("content", "").strip()
    return jsonify({
        "text": summary,
        "model": (data or {}).get("model", model or OLLAMA_MODEL),
    })


if __name__ == "__main__":
    if TLS_CERT and TLS_KEY:
        log.info("starting with TLS on %s:%d", HOST, PORT)
        app.run(host=HOST, port=PORT, ssl_context=(TLS_CERT, TLS_KEY))
    else:
        log.warning(
            "starting WITHOUT TLS on %s:%d - Office add-ins require HTTPS; "
            "terminate TLS at Caddy/Nginx or set TLS_CERT and TLS_KEY.",
            HOST, PORT,
        )
        app.run(host=HOST, port=PORT)
