from typing import Any
from django.http import HttpRequest, HttpResponsePermanentRedirect
from urllib.parse import urlencode

class CategoryRedirectMiddleware:
    """
    Redirects to the category detail page if the request is for the home page or the category page and has a category parameter.
    Reasson: We moved away from category filtering using query parameters and instead use the URL structure to filter by category.

    Example:
    - /agents/?category=open-source -> /categories/open-source/
    - /agents/?category=open-source&category=marketing -> /categories/open-source/
    """
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        if request.path in ['/agents/', '/'] and 'category' in request.GET:
            # Handle single category redirect
            categories = request.GET.getlist('category')
            redirect_url = f"/categories/{categories[0]}/"
            
            return HttpResponsePermanentRedirect(redirect_url)

        return self.get_response(request) 