# coding=utf-8
"""
吉客云库存现存量 → 本地 Inventory 同步
接口：erp.stockquantity.get

依赖：请先同步仓库与货品，缺失关联时跳过并记失败明细。
"""
import json
import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction

from basedata.models import Material, Measure, Warehouse
from invent.models import Inventory
from jackyun.client import JackyunAPIError, JackyunClient
from jackyun.models import JackyunSyncLog
from jackyun.sync_helpers import extract_list, to_decimal, truncate

logger = logging.getLogger(__name__)

WAREHOUSE_CODE_MAX = 6
GOODS_CODE_MAX = 20


def _get_or_create_measure(unit_name=None):
    """Inventory.measure 必填：优先用接口单位名，否则默认「件」"""
    name = truncate((unit_name or '').strip() or '件', 20)
    if name in ('默认', '缺省'):
        name = '件'
    measure = Measure.objects.filter(name=name).first()
    if measure:
        return measure
    code = truncate(name, 6) or 'PC'
    return Measure.objects.create(code=code, name=name, status=True)


def _ensure_material_measure(material, measure):
    """物料关联计量单位（ManyToMany）"""
    if not material.measure.filter(pk=measure.pk).exists():
        material.measure.add(measure)


def _row_warehouse_code(row):
    return row.get('warehouseCode') or row.get('code') or ''


def _row_goods_no(row):
    return row.get('goodsNo') or row.get('skuBarcode') or row.get('skuId') or ''


def _row_quantity(row):
    """优先现存量，其次可用量"""
    for key in ('currentQuantity', 'quantity', 'useQuantity', 'stockQuantity', 'cnt'):
        if row.get(key) not in (None, ''):
            return to_decimal(row.get(key))
    return Decimal('0')


@transaction.atomic
def upsert_inventory(row):
    """
    按仓库+物料 upsert 库存数量。
    :return: ('created'|'updated'|'skipped', Inventory|None)
    """
    wh_code = truncate(str(_row_warehouse_code(row)).strip(), WAREHOUSE_CODE_MAX)
    goods_no = truncate(str(_row_goods_no(row)).strip(), GOODS_CODE_MAX)
    if not wh_code:
        raise ValueError('库存缺少仓库编码')
    if not goods_no:
        raise ValueError('库存缺少货品编号')

    warehouse = Warehouse.objects.filter(code=wh_code).first()
    if not warehouse:
        raise ValueError('本地无仓库 code=%s，请先同步仓库' % wh_code)

    material = Material.objects.filter(code=goods_no).first()
    if not material:
        raise ValueError('本地无物料 code=%s，请先同步货品' % goods_no)

    measure = _get_or_create_measure(row.get('unitName'))
    _ensure_material_measure(material, measure)

    cnt = _row_quantity(row)
    price = to_decimal(row.get('costPrice') or row.get('price') or material.stock_price or 0)

    obj = Inventory.objects.filter(warehouse=warehouse, material=material).first()
    if obj:
        changed = False
        if obj.cnt != cnt:
            obj.cnt = cnt
            changed = True
        if obj.measure_id != measure.pk:
            obj.measure = measure
            changed = True
        if changed:
            Inventory.save(obj)
            return 'updated', obj
        return 'skipped', obj

    obj = Inventory(
        warehouse=warehouse,
        material=material,
        measure=measure,
        cnt=cnt,
        price=price,
    )
    Inventory.save(obj)
    return 'created', obj


def sync_inventory(page_size=50, client=None, dry_run=False):
    """分页拉取吉客云库存并写入本地 Inventory。"""
    log = JackyunSyncLog.objects.create(
        sync_type='inventory',
        status='running',
        message='开始同步库存（请先同步仓库与货品）',
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
            payload = client.stockquantity_get(**biz)
            rows = extract_list(
                payload,
                list_keys=(
                    'goodsStockQuantity', 'stockQuantitys', 'stockQuantities',
                    'stocks', 'quantityList', 'list', 'rows',
                ),
            )
            if not rows:
                if page_index == 0:
                    page_index = 1
                    payload = client.stockquantity_get(pageIndex=1, pageSize=page_size)
                    rows = extract_list(
                        payload,
                        list_keys=(
                            'goodsStockQuantity', 'stockQuantitys', 'stockQuantities',
                            'stocks', 'quantityList', 'list', 'rows',
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
                label = '%s/%s' % (_row_warehouse_code(row) or '?', _row_goods_no(row) or '?')
                try:
                    if dry_run:
                        skipped += 1
                        continue
                    action, _obj = upsert_inventory(row)
                    if action == 'created':
                        created += 1
                    elif action == 'updated':
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    errors.append('%s: %s' % (label, exc))
                    logger.exception('同步库存失败 %s', label)

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
