from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path(
        "stocks/search/",
        views.stock_search_suggestions,
        name="stock_search_suggestions",
    ),
    path("stocks/<int:stock_id>/", views.stock_detail, name="stock_detail"),
]
