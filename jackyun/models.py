# coding=utf-8
from django.db import models
from django.utils.translation import gettext_lazy as _


class JackyunSyncLog(models.Model):
    """吉客云同步日志"""

    STATUS_CHOICES = (
        ('running', '进行中'),
        ('success', '成功'),
        ('partial', '部分成功'),
        ('failed', '失败'),
    )

    sync_type = models.CharField('同步类型', max_length=40, default='sale_order')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='running')
    start_time = models.DateTimeField('查询开始时间', blank=True, null=True)
    end_time = models.DateTimeField('查询结束时间', blank=True, null=True)
    fetched = models.IntegerField('拉取条数', default=0)
    created = models.IntegerField('新建条数', default=0)
    skipped = models.IntegerField('跳过条数', default=0)
    failed = models.IntegerField('失败条数', default=0)
    message = models.TextField('说明', blank=True, null=True)
    detail = models.TextField('明细 JSON', blank=True, null=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    finished_at = models.DateTimeField('完成时间', blank=True, null=True)

    class Meta:
        verbose_name = '吉客云同步日志'
        verbose_name_plural = '吉客云同步日志'
        ordering = ['-id']

    def __str__(self):
        return '%s %s %s' % (self.sync_type, self.status, self.created_at)
