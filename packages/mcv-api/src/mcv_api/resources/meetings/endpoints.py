from ...core.constants import BASE_URL


def list_url(cv_cid: int) -> str:
    return f"{BASE_URL}/?q=courseville/course/{cv_cid}/meeting"
