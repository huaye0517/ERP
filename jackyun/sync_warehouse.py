# coding=utf-8
"""
吉客云仓库 → 本地 Warehouse 同步
接口：erp.warehouse.get
"""
import json
import logging
from datetime import datetime

from django.db import transaction

from basedata.models import Warehouse
from jackyun.client import JackyunAPIError, JackyunClient
from jackyun.models import JackyunSyncLog
from jackyun.sync_helpers import extract_list, is_blockup, truncate

logger = logging.getLogger(__name__)

# Warehouse.code 最大长度（const.DB_CHAR_CODE_6）
CODE_MAX = 6
NAME_MAX = 40
LOCATION_MAX = 120


def _warehouse_code(row):
    return (
        row.get('warehouseCode')
        or row.get('code')
        or row.get('warehouseId')
        or ''
    )


def _warehouse_name(row):
    return row.get('warehouseName') or row.get('name') or _warehouse_code(row) or '吉客云仓库'


@transaction.atomic
def upsert_warehouse(row):
    """
    按编码匹配/创建仓库。
    :return: ('created'|'updated'|'skipped', Warehouse|None)
    """
    raw_code = str(_warehouse_code(row)).strip()
    if not raw_code:
        raise ValueError('仓库缺少编码')

    code = truncate(raw_code, CODE_MAX)
    name = truncate(_warehouse_name(row), NAME_MAX)
    location = truncate(row.get('address') or row.get('location') or '', LOCATION_MAX) or None
    # isBlockup=1 表示停用
    blockup = is_blockup(row.get('isBlockup') or row.get('blockup') or row.get('isDelete'))
    status = not blockup

    obj = Warehouse.objects.filter(code=code).first()
    if obj:
        changed = False
        if obj.name != name:
            obj.name = name
            changed = True
        if location and obj.location != location:
            obj.location = location
            changed = True
        if obj.status != status:
            obj.status = status
            changed = True
        if changed:
            obj.save()
            return 'updated', obj
        return 'skipped', obj

    obj = Warehouse.objects.create(
        code=code,
        name=name,
        location=location,
        status=status,
    )
    return 'created', obj


def sync_warehouses(page_size=50, client=None, dry_run=False):
    """分页拉取吉客云仓库并写入本地 Warehouse。"""
    log = JackyunSyncLog.objects.create(
        sync_type='warehouse',
        status='running',
        message='开始同步仓库',
    )
    client = client or JackyunClient()
    page_size = min(max(int(page_size), 1), 200)
    page_index = 0
    fetched = created = updated = skipped = failed = 0
    errors = []

    try:
        while True:
            biz = {
                'pageIndex': page_index,
                'pageSize': page_size,
            }
            payload = client.warehouse_get(**biz)
            rows = extract_list(
                payload,
                list_keys=(
                    'warehouseInfo', 'warehouses', 'warehouseList',
                    'warehouse', 'list', 'rows',
                ),
            )
            if not rows:
                # 部分接口 pageIndex 从 1 起；第 0 页空则试第 1 页
                if page_index == 0:
                    page_index = 1
                    payload = client.warehouse_get(pageIndex=1, pageSize=page_size)
                    rows = extract_list(
                        payload,
                        list_keys=(
                            'warehouseInfo', 'warehouses', 'warehouseList',
                            'warehouse', 'list', 'rows',
                        ),
                    )
                    if not rows:
                        break
                else:
                    break

            for row in rows:
                if not isinstance(row, dict):
                    continue
                fetched += 1
                code = _warehouse_code(row) or '?'
                try:
                    if dry_run:
                        skipped += 1
                        continue
                    action, _obj = upsert_warehouse(row)
                    if action == 'created':
                        created += 1
                    elif action == 'updated':
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    errors.append('%s: %s' % (code, exc))
                    logger.exception('同步仓库失败 %s', code)

            if len(rows) < page_size:
                break
            page_index += 1

        if failed and (created or updated):
            status = 'partial'
        elif failed and not created and not updated:
            status = 'failed'
        else:
            status = 'success'

        log.status = status
        log.fetched = fetched
        log.created = created
        log.skipped = skipped + updated  # 日志模型无 updated 字段，更新计入 skipped 说明里体现
        log.failed = failed
        log.message = '拉取 %s，新建 %s，更新 %s，跳过 %s，失败 %s' % (
            fetched, created, updated, skipped, failed,
        )
        log.detail = json.dumps(errors[:50], ensure_ascii=False) if errors else None
        log.finished_at = datetime.now()
        log.save()
        return log

    except JackyunAPIError as exc:
        if created or updated:
            log.status = 'partial'
        else:
            log.status = 'failed'
        log.fetched = fetched
        log.created = created
        log.skipped = skipped + updated
        log.failed = failed
        log.message = '接口错误(已写入新建 %s/更新 %s): %s' % (created, updated, exc)
        log.detail = json.dumps(exc.payload, ensure_ascii=False)[:5000] if exc.payload else None
        log.finished_at = datetime.now()
        log.save()
        raise
    except Exception as exc:
        log.status = 'failed'
        log.message = '同步异常: %s' % exc
        log.finished_at = datetime.now()
        log.save()
        raise
