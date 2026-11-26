import requests

from . import config


def send(title: str, message: str, priority: str = "default", tags: str = "") -> bool:
    """ntfy par push (sirf signals). Headers latin-1 hote hain, isliye title/tags me emoji nahi."""
    # Safety net: error/warning type message kabhi phone par nahi jayega
    if "ERROR" in title.upper() or "warning" in tags.lower():
        print(f"[ntfy blocked: error message] {title} | {message}")
        return False

    if not config.NTFY_TOPIC:
        print(f"[ntfy skipped: NTFY_TOPIC set nahi] {title} | {message}")
        return False

    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    if config.NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {config.NTFY_TOKEN}"
    url = f"{config.NTFY_SERVER.rstrip('/')}/{config.NTFY_TOPIC}"
    r = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=20)
    r.raise_for_status()
    return True
