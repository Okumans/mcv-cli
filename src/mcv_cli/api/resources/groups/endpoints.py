from ...core.constants import BASE_URL, GROUP_LIST_URL


def page_url(cv_cid: int) -> str:
    return f"{BASE_URL}/?q=courseville/course/{cv_cid}/group"


def listing_url() -> str:
    return GROUP_LIST_URL
