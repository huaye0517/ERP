# coding=utf-8
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect
from django.utils.html import format_html

from jackyun.models import JackyunSyncLog
from jackyun.sync import sync_sale_orders
from jackyun.client import JackyunAPIError


@admin.register(JackyunSyncLog)
class JackyunSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'sync_type', 'status', 'start_time', 'end_time',
        'fetched', 'created', 'skipped', 'failed', 'created_at', 'finished_at',
    )
    list_filter = ('status', 'sync_type')
    readonly_fields = [f.name for f in JackyunSyncLog._meta.fields]
    ordering = ('-id',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['sync_button'] = format_html(
            '<a class="button" href="{}">立即同步最近7天销售单</a>',
            'sync-now/',
        )
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'sync-now/',
                self.admin_site.admin_view(self.sync_now_view),
                name='jackyun_sync_now',
            ),
        ]
        return custom + urls

    def sync_now_view(self, request):
        try:
            log = sync_sale_orders()
            messages.success(
                request,
                '同步完成：拉取 %s，新建 %s，跳过 %s，失败 %s' % (
                    log.fetched, log.created, log.skipped, log.failed,
                ),
            )
        except JackyunAPIError as exc:
            messages.error(request, '吉客云接口错误：%s' % exc)
        except Exception as exc:
            messages.error(request, '同步失败：%s' % exc)
        return redirect('admin:jackyun_jackyunsynclog_changelist')
