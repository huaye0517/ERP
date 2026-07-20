# coding=utf-8
"""
管理命令：从吉客云拉取仓库写入本地 ERP

示例：
  python manage.py sync_jackyun_warehouses
  python manage.py sync_jackyun_warehouses --page-size 100
  python manage.py sync_jackyun_warehouses --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from jackyun.client import JackyunAPIError
from jackyun.sync_warehouse import sync_warehouses


class Command(BaseCommand):
    help = '从吉客云同步仓库到本地'

    def add_arguments(self, parser):
        parser.add_argument('--page-size', type=int, default=50, help='每页条数，最大200')
        parser.add_argument('--dry-run', action='store_true', help='只拉取不写入')

    def handle(self, *args, **options):
        self.stdout.write('开始同步仓库…')
        try:
            log = sync_warehouses(
                page_size=options['page_size'],
                dry_run=options['dry_run'],
            )
        except JackyunAPIError as exc:
            raise CommandError('吉客云接口错误: %s' % exc) from exc

        self.stdout.write(self.style.SUCCESS(
            '完成 status=%s fetched=%s created=%s skipped=%s failed=%s' % (
                log.status, log.fetched, log.created, log.skipped, log.failed,
            )
        ))
        if log.message:
            self.stdout.write(log.message)
