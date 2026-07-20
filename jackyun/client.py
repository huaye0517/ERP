# coding=utf-8
"""
吉客云开放平台 HTTP 客户端（自研应用签名调用）
网关：https://open.jackyun.com/open/openapi/do
签名：md5(lower(secret + 固定顺序拼接参数 + secret))
"""
import hashlib
import json
import logging
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _json_dumps(obj):
    """紧凑 JSON，与签名字符串保持一致"""
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


class JackyunAPIError(Exception):
    """吉客云接口业务/协议错误"""

    def __init__(self, message, code=None, payload=None):
        super().__init__(message)
        self.code = code
        self.payload = payload


class JackyunClient:
    """
    吉客云开放平台客户端。
    自研应用无需 token；ISV 应用可在 settings 中配置 JACKYUN_TOKEN。
    """

    def __init__(self, app_key=None, app_secret=None, api_url=None, version=None, token=None):
        self.app_key = str(app_key or getattr(settings, 'JACKYUN_APP_KEY', '') or '')
        self.app_secret = str(app_secret or getattr(settings, 'JACKYUN_APP_SECRET', '') or '')
        self.api_url = api_url or getattr(
            settings, 'JACKYUN_API_URL', 'https://open.jackyun.com/open/openapi/do'
        )
        self.version = version or getattr(settings, 'JACKYUN_VERSION', '1.0')
        self.token = token if token is not None else getattr(settings, 'JACKYUN_TOKEN', '') or ''
        self.timeout = getattr(settings, 'JACKYUN_TIMEOUT', 60)

    def _ensure_credentials(self):
        if not self.app_key or not self.app_secret:
            raise JackyunAPIError('未配置 JACKYUN_APP_KEY / JACKYUN_APP_SECRET')

    def _sign(self, method, bizcontent, timestamp):
        """
        签名算法（与官方/社区 SDK 一致）：
        str = appkey{key}bizcontent{biz}contenttypeJSON method{m}timestamp{ts}version{v}
        sign = md5(lower(secret + str + secret))
        """
        sign_body = (
            f'appkey{self.app_key}'
            f'bizcontent{bizcontent}'
            f'contenttypeJSON'
            f'method{method}'
            f'timestamp{timestamp}'
            f'version{self.version}'
        )
        raw = (self.app_secret + sign_body + self.app_secret).lower()
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def call(self, method, biz=None):
        """
        调用开放平台接口。
        :param method: 如 oms.trade.fullinfoget
        :param biz: 业务参数 dict，将序列化为 bizcontent
        :return: 完整响应 dict
        """
        self._ensure_credentials()
        biz = biz or {}
        bizcontent = _json_dumps(biz)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        params = {
            'method': method,
            'appkey': self.app_key,
            'version': self.version,
            'contenttype': 'json',
            'timestamp': timestamp,
            'bizcontent': bizcontent,
            'sign': self._sign(method, bizcontent, timestamp),
        }
        if self.token:
            params['token'] = self.token

        logger.debug('Jackyun call %s', method)
        resp = requests.post(
            self.api_url,
            data=params,
            headers={'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            raise JackyunAPIError('吉客云返回非 JSON：%s' % resp.text[:200]) from exc

        code = payload.get('code')
        msg = payload.get('msg') or payload.get('message') or ''
        sub_code = payload.get('subCode') or payload.get('sub_code')
        result = payload.get('result') if isinstance(payload.get('result'), dict) else {}
        data = result.get('data') if result else None

        # 200 为明确成功；0 在无数据且带 subCode/错误文案时视为失败
        if code in (200, '200'):
            return payload
        if code in (0, '0', None):
            err_hint = any(k in str(msg) for k in ('无法', '失败', '错误', '未开通', '无权限'))
            if data is None and (sub_code or err_hint):
                raise JackyunAPIError(msg or '接口调用失败', code=code, payload=payload)
            return payload
        raise JackyunAPIError(msg or '接口调用失败', code=code, payload=payload)

    def trade_fullinfo_get(self, **biz):
        """销售单查询 oms.trade.fullinfoget"""
        return self.call('oms.trade.fullinfoget', biz)

    def trade_count_get(self, **biz):
        """销售单总数查询 oms.trade.countget"""
        return self.call('oms.trade.countget', biz)

    def goods_list_get(self, **biz):
        """货品档案列表 erp.storage.goodslist"""
        return self.call('erp.storage.goodslist', biz)

    def warehouse_get(self, **biz):
        """仓库查询 erp.warehouse.get"""
        return self.call('erp.warehouse.get', biz)

    def stockquantity_get(self, **biz):
        """库存现存量查询 erp.stockquantity.get"""
        return self.call('erp.stockquantity.get', biz)
