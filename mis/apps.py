# -*- coding: utf-8 -*-
from django.apps import AppConfig


class MisConfig(AppConfig):
    name = 'mis'
    verbose_name = 'Django-ERP'

    def ready(self):
        from django.contrib import admin
        admin.site.site_header = 'Django-ERP'
        admin.site.site_title = 'ERP'
        admin.site.index_title = '系统管理'
