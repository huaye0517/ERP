# coding=utf-8
"""
吉客云货品档案 → 本地 Material 同步
接口：erp.storage.goodslist

数据量超过 1 万时平台要求用游标：pageIndex 固定 0，传 maxSkuId（上次最大 skuId，首次 0）。
"""
import json
import logging
from datetime import datetime

from django.db import transaction

from basedata.models import Material
from jackyun.client import JackyunAPIError, JackyunClient
from jackyun.models import JackyunSyncLog
from jackyun.sync_helpers import extract_list, is_blockup, truncate

logger = logging.getLogger(__name__)

CODE_MAX = 20
NAME_MAX = 120
SPEC_MAX = 120
BARCODE_MAX = 40


def _goods_no(row):
    return (
        row.get('goodsNo')
        or row.get('skuBarcode')
        or row.get('skuId')
        or row.get('outerId')
        or ''
    )


def _goods_name(row):
    return (
        row.get('goodsName')
        or row.get('skuName')
        or row.get('name')
        or _goods_no(row)
        or '吉客云货品'
    )


def _sku_id(row):
    """游标字段：skuId（字符串或数字）"""
    val = row.get('skuId')
    if val is None or val == '':
        return None
    return str(val)


@transaction.atomic
def upsert_goods(row):
    """
    按货品编号匹配/创建物料。
    :return: ('created'|'updated'|'skipped', Material|None)
    """
    raw_code = str(_goods_no(row)).strip()
    if not raw_code:
        raise ValueError('货品缺少编号')

    code = truncate(raw_code, CODE_MAX)
    name = truncate(_goods_name(row), NAME_MAX)
    spec = truncate(
        row.get('skuName') or row.get('specName') or row.get('spec') or '',
        SPEC_MAX,
    ) or None
    barcode = truncate(
        row.get('skuBarcode') or row.get('barcode') or '',
        BARCODE_MAX,
    ) or None
    blockup = is_blockup(
        row.get('isBlockup')
        or row.get('skuIsBlockup')
        or row.get('goodsIsBlockup')
        or row.get('blockup')
    )
    status = not blockup

    obj = Material.objects.filter(code=code).first()
    if obj:
        changed = False
        if obj.name != name:
            obj.name = name
            changed = True
        if spec is not None and obj.spec != spec:
            obj.spec = spec
            changed = True
        if barcode is not None and obj.barcode != barcode:
            obj.barcode = barcode
            changed = True
        if obj.status != status:
            obj.status = status
            changed = True
        if changed:
            Material.save(obj)
            return 'updated', obj
        return 'skipped', obj

    obj = Material(
        code=code,
        name=name,
        spec=spec,
        barcode=barcode,
        can_sale=True,
        status=status,
    )
    Material.save(obj)
    return 'created', obj


def sync_goods(page_size=50, client=None, dry_run=False):
    """
    拉取吉客云货品并写入本地 Material。
    使用 maxSkuId 游标分页（pageIndex 固定为 0），避免超 1 万条时报错。
    """
    log = JackyunSyncLog.objects.create(
        sync_type='goods',
        status='running',
        message='开始同步货品（maxSkuId 游标）',
    )
    client = client or JackyunClient()
    page_size = min(max(int(page_size), 1), 200)
    max_sku_id = '0'
    fetched = created = updated = skipped = failed = 0
    errors = []
    seen_cursors = set()

    try:
        while True:
            if max_sku_id in seen_cursors:
                break
            seen_cursors.add(max_sku_id)

            biz = {
                'pageIndex': 0,
                'pageSize': page_size,
                'maxSkuId': max_sku_id,
            }
            payload = client.goods_list_get(**biz)
            rows = extract_list(
                payload,
                list_keys=('goods', 'goodsList', 'skuList', 'skus', 'list', 'rows'),
            )
            if not rows:
                break

            last_sku = None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                fetched += 1
                code = _goods_no(row) or '?'
                sid = _sku_id(row)
                if sid:
                    last_sku = sid
                try:
                    if dry_run:
                        skipped += 1
                        continue
                    action, _obj = upsert_goods(row)
                    if action == 'created':
                        created += 1
                    elif action == 'updated':
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    errors.append('%s: %s' % (code, exc))
                    logger.exception('同步货品失败 %s', code)

            if not last_sku or last_sku == max_sku_id:
                break
            if len(rows) < page_size:
                # 本页不足仍推进游标，避免漏数；下一轮若空则退出
                max_sku_id = last_sku
                continue
            max_sku_id = last_sku

        if failed and (created or updated):
            status = 'partial'
        elif failed and not created and not updated:
            status = 'failed'
        else:
            status = 'success'

        log.status = status
        log.fetched = fetched
        log.created = created
        log.skipped = skipped + updated
        log.failed = failed
        log.message = '拉取 %s，新建 %s，更新 %s，跳过 %s，失败 %s' % (
            fetched, created, updated, skipped, failed,
        )
        log.detail = json.dumps(errors[:50], ensure_ascii=False) if errors else None
        log.finished_at = datetime.now()
        log.save()
        return log

    except JackyunAPIError as exc:
        # 中途限流等情况：已有写入则记为部分成功
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
