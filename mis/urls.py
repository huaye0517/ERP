from django.urls import include, re_path, path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
import workflow.views
import invent.urls
import basedata.urls
import selfhelp.urls
import mis.views

urlpatterns = [
    re_path(r'^$', mis.views.home),
    re_path(r"^admin/(?P<app>\w+)/(?P<model>\w+)/(?P<object_id>\d+)/start", workflow.views.start),
    re_path(r"^admin/(?P<app>\w+)/(?P<model>\w+)/(?P<object_id>\d+)/approve/(?P<operation>\d+)", workflow.views.approve),
    re_path(r"^admin/(?P<app>\w+)/(?P<model>\w+)/(?P<object_id>\d+)/restart/(?P<instance>\d+)", workflow.views.restart),
    path('admin/', admin.site.urls),
    path('admin/invent/', include(invent.urls)),
    path('admin/basedata/', include(basedata.urls)),
    path('admin/selfhelp/', include(selfhelp.urls)),
]
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
