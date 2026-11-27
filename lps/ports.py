"""Saved COM choices plus current discovery. Never selects a port or opens hardware."""
import re

def choices(settings, detected=(), current=""):
    saved = settings.get("known_ports") or []
    if isinstance(saved, str):
        saved = [saved]
    candidates = list(saved) + [settings.get("port", ""), current] + [port for port, _ in detected]
    values = {str(port).strip().upper() for port in candidates if str(port).strip()}
    def key(port):
        match = re.fullmatch(r"COM(\d+)", port)
        return (0, int(match[1])) if match else (1, port)
    return sorted(values, key=key)

def description(options, detected):
    found = {port.upper(): text for port, text in detected}
    return "\n".join(f"{port}: {found[port]}" if port in found else
                     f"{port}: saved choice, not detected now" for port in options)
