from ...core.constants import BASE_URL


def detail_url(cv_cid: int) -> str:
    return f"{BASE_URL}/?q=courseville/course/{cv_cid}/playlist"


def loaded_detail_url() -> str:
    """Return the read-only endpoint used to hydrate deferred playlist clips."""

    return f"{BASE_URL}/?q=cvdlit/ajax/loadedlaterplaylistdetail"
