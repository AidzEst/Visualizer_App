from django.contrib import admin
from django.urls import path
from myapp import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('loginpage/', views.loginpage, name='loginpage'),
    path('convert/', views.convert, name='convert'),
    path('import_file', views.import_file, name='import_file'),
    path('clean/', views.clean, name='clean'),
    path('download_clean/', views.download_clean, name='download_clean'),
    path('visualize/', views.visualize, name='visualize'),
    path('createuser/', views.create_user, name='createuser'),
    path('', views.homepage, name='homepage'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)