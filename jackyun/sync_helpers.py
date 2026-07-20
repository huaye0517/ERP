# coding=utf-8
"""吉客云同步共用辅助函数"""
from decimal import Decimal, InvalidOperation


def truncate(text, length):
    if text is None:
        return ''
    text = str(text)
    return text[:length] if len(text) > length else text


def to_decimal(value, default='0'):
    if value is None or value == '':
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def extract_list(payload, list_keys=None):
    """
    从吉客云分页接口响应中取出列表。
    list_keys: 候选字段名，如 ('goods', 'goodsList', 'warehouses')
    """
    list_keys = list_keys or ()
    result = payload.get('result') or {}
    data = result.get('data') if isinstance(result, dict) else result

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in list_keys:
        items = data.get(key)
        if isinstance(items, list):
            return items

    # 常见兜底：data 下唯一的 list 字段
    for key, value in data.items():
        if isinstance(value, list) and key not in ('fields',):
            return value

    # 再兜一层：result 本身是列表容器
    if isinstance(result, dict):
        for key in list_keys:
            items = result.get(key)
            if isinstance(items, list):
                return items

    return []


def is_blockup(value):
    """吉客云停用标记：1/true/'1'/'true'/'Y' 视为停用"""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in ('1', 'true', 'y', 'yes')
