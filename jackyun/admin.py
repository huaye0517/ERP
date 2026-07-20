# coding=utf-8
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from jackyun.models import JackyunSyncLog
from jackyun.sync import sync_sale_orders
from jackyun.sync_warehouse import sync_warehouses
from jackyun.sync_goods import sync_goods
from jackyun.sync_inventory import sync_inventory
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
        # 多个同步按钮：销售单 / 仓库 / 货品 / 库存
        buttons = [
            ('sync-now/', '立即同步最近7天销售单'),
            ('sync-warehouses/', '同步仓库'),
            ('sync-goods/', '同步货品'),
            ('sync-inventory/', '同步库存'),
        ]
        extra_context['sync_buttons'] = mark_safe(''.join(
            format_html('<a class="button" href="{}">{}</a> ', href, label)
            for href, label in buttons
        ))
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'sync-now/',
                self.admin_site.admin_view(self.sync_now_view),
                name='jackyun_sync_now',
            ),
            path(
                'sync-warehouses/',
                self.admin_site.admin_view(self.sync_warehouses_view),
                name='jackyun_sync_warehouses',
            ),
            path(
                'sync-goods/',
                self.admin_site.admin_view(self.sync_goods_view),
                name='jackyun_sync_goods',
            ),
            path(
                'sync-inventory/',
                self.admin_site.admin_view(self.sync_inventory_view),
                name='jackyun_sync_inventory',
            ),
        ]
        return custom + urls

    def _run_sync(self, request, sync_fn, label):
        try:
            log = sync_fn()
            messages.success(
                request,
                '%s完成：拉取 %s，新建 %s，跳过 %s，失败 %s' % (
                    label, log.fetched, log.created, log.skipped, log.failed,
                ),
            )
            if log.message:
                messages.info(request, log.message)
        except JackyunAPIError as exc:
            messages.error(request, '吉客云接口错误：%s' % exc)
        except Exception as exc:
            messages.error(request, '%s失败：%s' % (label, exc))
        return redirect('admin:jackyun_jackyunsynclog_changelist')

    def sync_now_view(self, request):
        return self._run_sync(request, sync_sale_orders, '销售单同步')

    def sync_warehouses_view(self, request):
        return self._run_sync(request, sync_warehouses, '仓库同步')

    def sync_goods_view(self, request):
        return self._run_sync(request, sync_goods, '货品同步')

    def sync_inventory_view(self, request):
        return self._run_sync(request, sync_inventory, '库存同步')
