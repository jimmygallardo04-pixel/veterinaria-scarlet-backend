from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class ClinicPagination(PageNumberPagination):
    page_size = getattr(settings, "API_PAGE_SIZE", 20)
    page_size_query_param = "page_size"
    max_page_size = getattr(settings, "API_MAX_PAGE_SIZE", 100)
