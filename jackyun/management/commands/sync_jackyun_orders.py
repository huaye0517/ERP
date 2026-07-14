# coding=utf-8
"""
管理命令：从吉客云拉取销售单写入本地 ERP

示例：
  python manage.py sync_jackyun_orders
  python manage.py sync_jackyun_orders --days 3
  python manage.py sync_jackyun_orders --start "2026-07-07 00:00:00" --end "2026-07-14 23:59:59"
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from jackyun.client import JackyunAPIError
from jackyun.sync import sync_sale_orders


class Command(BaseCommand):
    help = '从吉客云同步销售单到本地（时间跨度不超过7天）'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='回溯天数，默认7，最大7')
        parser.add_argument('--start', type=str, default='', help='开始时间 YYYY-MM-DD HH:MM:SS')
        parser.add_argument('--end', type=str, default='', help='结束时间 YYYY-MM-DD HH:MM:SS')
        parser.add_argument('--page-size', type=int, default=50, help='每页条数，最大200')
        parser.add_argument('--dry-run', action='store_true', help='只拉取不写入')

    def handle(self, *args, **options):
        end = datetime.now()
        start = end - timedelta(days=min(max(options['days'], 1), 7))
        if options['start']:
            try:
                start = datetime.strptime(options['start'], '%Y-%m-%d %H:%M:%S')
            except ValueError as exc:
                raise CommandError('start 格式应为 YYYY-MM-DD HH:MM:SS') from exc
        if options['end']:
            try:
                end = datetime.strptime(options['end'], '%Y-%m-%d %H:%M:%S')
            except ValueError as exc:
                raise CommandError('end 格式应为 YYYY-MM-DD HH:MM:SS') from exc

        self.stdout.write('同步窗口: %s ~ %s' % (start, end))
        try:
            log = sync_sale_orders(
                start=start,
                end=end,
                page_size=options['page_size'],
                dry_run=options['dry_run'],
            )
        except JackyunAPIError as exc:
            raise CommandError('吉客云接口错误: %s' % exc) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            '完成 status=%s fetched=%s created=%s skipped=%s failed=%s' % (
                log.status, log.fetched, log.created, log.skipped, log.failed,
            )
        ))
        if log.message:
            self.stdout.write(log.message)
