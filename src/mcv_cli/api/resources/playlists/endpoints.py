from ...core.constants import BASE_URL


def detail_url(cv_cid: int) -> str:
    return f"{BASE_URL}/?q=courseville/course/{cv_cid}/playlist"
