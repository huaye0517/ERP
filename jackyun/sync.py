# coding=utf-8
"""
吉客云销售单 → 本地 SaleOrder / SaleItem 同步服务
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from basedata.models import Material, Partner
from jackyun.client import JackyunAPIError, JackyunClient
from jackyun.models import JackyunSyncLog
from sale.models import SaleItem, SaleOrder

logger = logging.getLogger(__name__)

# 销售单查询需要返回的字段（含 scrollId 以便游标翻页）
TRADE_FIELDS = ','.join([
    'tradeNo',
    'sourceTradeNo',
    'shopName',
    'companyName',
    'customerName',
    'customerAccount',
    'tradeTime',
    'billDate',
    'gmtCreate',
    'totalFee',
    'payment',
    'discountFee',
    'receiverName',
    'mobile',
    'phone',
    'address',
    'buyerMemo',
    'sellerMemo',
    'remark',
    'tradeStatus',
    'goodsDetail.goodsNo',
    'goodsDetail.goodsName',
    'goodsDetail.sellCount',
    'goodsDetail.sellPrice',
    'goodsDetail.discountFee',
    'goodsDetail.shareOrderDiscountFee',
    'goodsDetail.specName',
    'scrollId',
])


def _to_decimal(value, default='0'):
    if value is None or value == '':
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _parse_datetime(value):
    """解析吉客云常见时间字符串，失败返回 None"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt, size in (
        ('%Y-%m-%d %H:%M:%S', 19),
        ('%Y-%m-%d %H:%M', 16),
        ('%Y-%m-%d', 10),
    ):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    return None


def _parse_date(value, fallback=None):
    dt = _parse_datetime(value)
    if dt:
        return dt.date()
    return fallback or datetime.today().date()


def _truncate(text, length):
    if text is None:
        return ''
    text = str(text)
    return text[:length] if len(text) > length else text


def _extract_trades(payload):
    """从 fullinfoget 响应中取出订单列表与下一页 scrollId"""
    result = payload.get('result') or {}
    data = result.get('data') if isinstance(result, dict) else result
    trades = []
    scroll_id = ''
    if isinstance(data, dict):
        trades = data.get('trades') or data.get('trade') or []
        scroll_id = data.get('scrollId') or ''
        if not trades and isinstance(data.get('data'), list):
            trades = data.get('data')
    elif isinstance(data, list):
        trades = data
    if not isinstance(trades, list):
        trades = []
    # 部分返回把 scrollId 放在订单对象上
    if not scroll_id and trades:
        last = trades[-1]
        if isinstance(last, dict):
            scroll_id = last.get('scrollId') or ''
    return trades, scroll_id


def _get_or_create_partner(trade):
    """按客户名称匹配/创建客户（合作伙伴）"""
    name = (
        trade.get('customerName')
        or trade.get('companyName')
        or trade.get('shopName')
        or '吉客云客户'
    )
    name = _truncate(name, 120)
    partner = Partner.objects.filter(partner_type='C', name=name).first()
    if partner:
        return partner
    code_src = trade.get('customerAccount') or trade.get('shopName') or name
    code = _truncate('JKY-%s' % code_src, 20)
    partner = Partner.objects.create(
        code=code,
        name=name,
        partner_type='C',
        contacts=_truncate(trade.get('receiverName') or '', 40) or None,
        phone=_truncate(trade.get('mobile') or trade.get('phone') or '', 40) or None,
        memo='由吉客云销售单同步自动创建',
    )
    return partner


def _get_or_create_material(goods):
    """按货品编号匹配/创建物料（不设售价，避免覆盖同步明细价）"""
    goods_no = (goods.get('goodsNo') or goods.get('outerId') or '').strip()
    goods_name = (goods.get('goodsName') or goods_no or '吉客云货品').strip()
    material = None
    if goods_no:
        material = Material.objects.filter(code=goods_no).first()
    if not material:
        material = Material.objects.filter(name=goods_name).first()
    if material:
        return material
    return Material.objects.create(
        code=_truncate(goods_no or 'JKY', 20) or None,
        name=_truncate(goods_name, 120),
        spec=_truncate(goods.get('specName') or '', 120) or None,
        can_sale=True,
        status=True,
    )


def _goods_list(trade):
    detail = trade.get('goodsDetail') or trade.get('goodsDetails') or []
    if isinstance(detail, dict):
        # 有的返回包一层
        if 'goods' in detail:
            detail = detail['goods']
        else:
            detail = [detail]
    if not isinstance(detail, list):
        return []
    return detail


@transaction.atomic
def upsert_sale_order(trade):
    """
    将单条吉客云销售单写入本地。
    以 tradeNo 作为 SaleOrder.code 做幂等：已存在则跳过。
    :return: ('created'|'skipped', SaleOrder|None)
    """
    trade_no = (trade.get('tradeNo') or '').strip()
    if not trade_no:
        raise ValueError('销售单缺少 tradeNo')

    code = _truncate(trade_no, 20)
    existing = SaleOrder.objects.filter(code=code).first()
    if existing:
        return 'skipped', existing

    order_date = _parse_date(
        trade.get('tradeTime') or trade.get('billDate') or trade.get('gmtCreate')
    )
    deliver_date = order_date + timedelta(days=7)
    partner = _get_or_create_partner(trade)
    shop = trade.get('shopName') or ''
    title = _truncate(shop and ('吉客云-%s' % shop) or ('吉客云订单 %s' % trade_no), 40)
    memo_parts = []
    if trade.get('sourceTradeNo'):
        memo_parts.append('网店单号:%s' % trade.get('sourceTradeNo'))
    if trade.get('buyerMemo'):
        memo_parts.append('买家:%s' % trade.get('buyerMemo'))
    if trade.get('sellerMemo'):
        memo_parts.append('卖家:%s' % trade.get('sellerMemo'))
    if trade.get('remark'):
        memo_parts.append(str(trade.get('remark')))
    memo_parts.append('吉客云同步 tradeNo=%s' % trade_no)

    order = SaleOrder(
        code=code,
        partner=partner,
        order_date=order_date,
        deliver_date=deliver_date,
        title=title,
        description='\n'.join(memo_parts),
        contact=_truncate(trade.get('receiverName') or '', 20) or None,
        phone=_truncate(trade.get('mobile') or trade.get('phone') or '', 20) or None,
        deliver_address=_truncate(trade.get('address') or '', 120) or None,
        amount=_to_decimal(trade.get('payment') or trade.get('totalFee')),
        discount_amount=_to_decimal(trade.get('discountFee')),
        status='0',
    )
    # 直接 Model.save，避免 BOAdmin 改写 code
    SaleOrder.save(order)

    for goods in _goods_list(trade):
        material = _get_or_create_material(goods)
        cnt = _to_decimal(goods.get('sellCount') or goods.get('baseUnitSellCount') or 1, '1')
        if cnt <= 0:
            cnt = Decimal('1')
        price = _to_decimal(goods.get('sellPrice'))
        discount = price
        share = goods.get('shareOrderDiscountFee') or goods.get('discountFee')
        if share not in (None, ''):
            # 简单均摊到单价上：原价 - 分摊优惠/数量
            try:
                discount = price - (_to_decimal(share) / cnt)
                if discount < 0:
                    discount = Decimal('0')
            except Exception:
                discount = price
        item = SaleItem(
            master=order,
            material=material,
            cnt=cnt,
            sale_price=price,
            discount_price=discount,
        )
        # 物料未设售价时，SaleItem.save 不会覆盖我们写入的单价
        item.save()

    return 'created', order


def sync_sale_orders(start=None, end=None, page_size=50, client=None, dry_run=False):
    """
    按修改时间窗口拉取吉客云销售单并写入本地。
    时间跨度不能超过 7 天（平台限制）。
    """
    now = datetime.now()
    if end is None:
        end = now
    if start is None:
        start = end - timedelta(days=7)
    if (end - start).total_seconds() > 7 * 24 * 3600 + 60:
        raise ValueError('查询时间跨度不能超过 7 天')

    start_str = start.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end.strftime('%Y-%m-%d %H:%M:%S')

    log = JackyunSyncLog.objects.create(
        sync_type='sale_order',
        status='running',
        start_time=start,
        end_time=end,
        message='开始同步 %s ~ %s' % (start_str, end_str),
    )

    client = client or JackyunClient()
    scroll_id = ''
    fetched = created = skipped = failed = 0
    errors = []

    try:
        while True:
            biz = {
                'pageSize': min(int(page_size), 200),
                'startModified': start_str,
                'endModified': end_str,
                'fields': TRADE_FIELDS,
                'scrollId': scroll_id,
                'hasTotal': 0,
            }
            payload = client.trade_fullinfo_get(**biz)
            trades, next_scroll = _extract_trades(payload)
            if not trades:
                break

            for trade in trades:
                fetched += 1
                trade_no = (trade.get('tradeNo') if isinstance(trade, dict) else None) or '?'
                try:
                    if dry_run:
                        skipped += 1
                        continue
                    action, _obj = upsert_sale_order(trade)
                    if action == 'created':
                        created += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    errors.append('%s: %s' % (trade_no, exc))
                    logger.exception('同步销售单失败 %s', trade_no)

            # 无下一页游标或本页不足则结束
            if not next_scroll or next_scroll == scroll_id:
                break
            scroll_id = next_scroll

        if failed and created:
            status = 'partial'
        elif failed and not created:
            status = 'failed'
        else:
            status = 'success'

        log.status = status
        log.fetched = fetched
        log.created = created
        log.skipped = skipped
        log.failed = failed
        log.message = '拉取 %s，新建 %s，跳过 %s，失败 %s' % (fetched, created, skipped, failed)
        log.detail = json.dumps(errors[:50], ensure_ascii=False) if errors else None
        log.finished_at = datetime.now()
        log.save()
        return log

    except JackyunAPIError as exc:
        log.status = 'failed'
        log.fetched = fetched
        log.created = created
        log.skipped = skipped
        log.failed = failed
        log.message = '接口错误: %s' % exc
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
