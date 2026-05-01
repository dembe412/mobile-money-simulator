import re


def normalize_phone(phone: str) -> str:
    """Normalize phone numbers to a simple digits-only local format.

    - Strips all non-digit characters
    - Keeps leading country code if present (does not attempt full E.164 conversion)
    """
    if not phone:
        return ""
    s = re.sub(r"\D", "", phone)
    return s
