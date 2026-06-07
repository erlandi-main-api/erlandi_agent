import json
import requests
from tools import SCHEMA, dispatch

MAX_ITER = 12
TRUNCATE = 2500


def run(provider, messages, on_update=None):
    """
    Agent loop. messages = full list including system + history + user.
    on_update(text) called with tool status updates.
    Returns final response string.
    """
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json"
    }

    base = provider["base_url"].rstrip("/")
    # Minimax special endpoint
    if "minimax" in base:
        gid = provider.get("group_id", "")
        ep = f"{base}/text/chatcompletion_v2"
        if gid:
            ep += f"?GroupId={gid}"
    else:
        ep = f"{base}/chat/completions"

    for _ in range(MAX_ITER):
        payload = {
            "model":    provider["model"],
            "messages": messages,
            "temperature": 0.7,
            "tools":    SCHEMA,
            "tool_choice": "auto",
        }

        try:
            resp = requests.post(ep, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.HTTPError as e:
            return f"HTTP {e.response.status_code}: {e.response.text[:300]}"
        except Exception as e:
            return f"Error: {e}"

        choice  = data["choices"][0]
        msg     = choice["message"]
        reason  = choice.get("finish_reason", "stop")

        messages.append(msg)

        # No tool calls — done
        if reason == "stop" or not msg.get("tool_calls"):
            return (msg.get("content") or "").strip()

        # Execute tools
        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}

            if on_update:
                arg_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
                on_update(f"⚙️ `{name}({arg_str})`")

            result = dispatch(name, args)

            if on_update:
                preview = result[:400] + "…" if len(result) > 400 else result
                on_update(f"```\n{preview}\n```")

            truncated = result[:TRUNCATE] + "…" if len(result) > TRUNCATE else result
            messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      truncated,
            })

    return "Max iterations reached."
