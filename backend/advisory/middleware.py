"""
advisory/middleware.py

Adds Cache-Control: no-cache headers to all API responses so the browser
always fetches fresh data instead of serving a stale cached copy — fixes the
bug where dashboard weather / disease / alert data doesn't update on page refresh.
"""


class NoCacheMiddleware:
    """
    Add no-cache headers to every response so browsers and proxies never cache
    our JSON API responses. Static files (JS/CSS/images served by Vite, not Django)
    are unaffected — this only applies to paths under /api/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
