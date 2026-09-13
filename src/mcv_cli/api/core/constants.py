"""Official MyCourseVille endpoints used by the pure API layer."""

BASE_URL = "https://www.mycourseville.com"
PUBLIC_AUTHORIZATION_URL = f"{BASE_URL}/api/oauth/authorize"
PUBLIC_CLIENT_ID = "mycourseville.com"
PUBLIC_REDIRECT_URI = BASE_URL
PLATFORM_LOGIN_URL = f"{BASE_URL}/api/login"
CHULA_LOGIN_URL = f"{BASE_URL}/api/chulalogin"
API_PREFIX = "/api/v1/public"
COURSE_HOME_URL = f"{BASE_URL}/?q=courseville"
COURSE_FILTER_URL = f"{BASE_URL}/?q=courseville/ajax/cvhomepanel_get_filter"
COURSE_AJAX_URL = f"{BASE_URL}/?q=courseville/ajax/course"
GROUP_LIST_URL = f"{BASE_URL}/?q=courseville/ajax/cvpagegroup_getgroupcardlisting"
