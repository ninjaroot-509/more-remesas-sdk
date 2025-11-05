from __future__ import annotations

SENSITIVE_KEYS = {"LoginUser", "LoginPass", "AccessToken"}

def redact(value: str) -> str:
    if not value:
        return value
    if len(value) <= 6:
        return "******"
    return value[:3] + "****" + value[-2:]

def sanitize_headers(headers: dict) -> dict:
    out = {}
    for k, v in headers.items():
        if any(s in k for s in ("Authorization", "Cookie", "Set-Cookie")):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out

def scrub_xml(xml: str) -> str:
    out = xml
    for tag in ("LoginUser", "LoginPass", "AccessToken"):
        out = out.replace(f"<{tag}>", f"<{tag}>****").replace(f"</{tag}>", f"</{tag}>")
    return out
