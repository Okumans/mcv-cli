from ...core.constants import BASE_URL


def detail_url(cv_cid: int, item_id: int) -> str:
    return f"{BASE_URL}/?q=courseville/course/{cv_cid}/view_content_node_{item_id}"
