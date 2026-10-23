"""Historical competitor prices, never a live quote or our provider cost.

Source snapshot: research/sites/03.json and research/evidence/03/pricing.txt
(2026-10-23); pricing.html's JSON-LD confirms USD. No network is used.
"""

SOURCE_URL = 'https://rapreel.com/pricing'
CHECKED_AT = '2026-10-23'
_PLANS = {
    (8, '480p'): ('Lite', 2.99),
    (12, '720p'): ('HD', 3.99),
    (15, '720p'): ('Pro', 5.99),
}
_REQUIRED = frozenset(('duration_seconds', 'quality', 'aspect_ratio'))
_ALLOWED = _REQUIRED | {'site_id'}
_ASSUMPTIONS = (
    '历史官网参考报价，来源核查日期 2026-10-23；非实时、非结账或发票，未付款核验，税费及最终实付待核。',
    '这是竞品成片按条套餐参考，不是自建服务的供应商成本；真实供应商成本待核。',
    '仅逐项匹配官网一次性套餐，不按秒线性推算，不将无匹配视为免费或零价。',
    '各站 credits 的计量与权益不同，不能跨站换算；年付折月金额不能视作逐月付款或单条价格。',
)


def quote(payload):
    """Return a source-backed comparable price, or null with a reason.

    Only site 03 is supported. The workbench maps its 9:16 option to the
    source's "vertical" wording; the source does not confirm that exact ratio.
    Unsupported string-valued specs/sites are valid requests with no match.
    Malformed fields/types raise ValueError for the HTTP layer's 400 response.
    """
    if not isinstance(payload, dict):
        raise ValueError('quote payload: expected an object')
    unknown = set(payload) - _ALLOWED
    if unknown:
        raise ValueError('unknown quote fields: ' + ', '.join(sorted(map(repr, unknown))))
    missing = _REQUIRED - set(payload)
    if missing:
        raise ValueError('missing quote fields: ' + ', '.join(sorted(missing)))
    duration = payload['duration_seconds']
    if type(duration) is not int or duration <= 0:
        raise ValueError('duration_seconds: expected a positive integer (not boolean)')
    for field in ('quality', 'aspect_ratio', 'site_id'):
        if field in payload and (not isinstance(payload[field], str) or not payload[field].strip()):
            raise ValueError(field + ': expected a nonempty string')

    site_id = payload.get('site_id', '03')
    result = {
        'estimate': None,
        'currency': 'USD' if site_id == '03' else None,
        'basis': '',
        'assumptions': list(_ASSUMPTIONS),
        'is_vendor_quote': False,
        'quote_kind': 'competitor_reference',
        'source_url': SOURCE_URL if site_id == '03' else None,
        'checked_at': CHECKED_AT if site_id == '03' else None,
        'site_id': site_id,
        'matched_spec': None,
    }
    if site_id != '03':
        result['basis'] = '无可比报价：该站点尚未支持；当前只匹配研究条目 03 RapReel 的历史一次性套餐。无报价不代表免费或零价。'
        return result

    result['assumptions'].append(
        '工作台将 9:16 映射为官网的 vertical（竖屏），这是映射推断；官网未声明精确 9:16 尺寸，购买前需确认。'
    )
    result['assumptions'].append('RapReel 的免费内容是静态舞台预览，不能当作免费视频成片。')
    if payload['aspect_ratio'] != '9:16':
        result['basis'] = '无可比报价：官网套餐只声明竖屏，本工作台仅支持 9:16 的竖屏映射；请求的画幅无来源支持。无报价不代表免费或零价。'
        return result
    plan = _PLANS.get((duration, payload['quality']))
    if plan is None:
        result['basis'] = '无可比报价：时长与画质必须精确匹配 8 秒/480p、12 秒/720p 或 15 秒/720p；不插值或按秒外推。无报价不代表免费或零价。'
        return result
    name, amount = plan
    result['estimate'] = amount
    result['basis'] = (
        f'RapReel {name} 历史官网套餐：{duration} 秒 / {payload["quality"]} / 竖屏，'
        f'每条一次性 {amount:.2f} USD（{CHECKED_AT} 核查）；9:16 仅为工作台竖屏映射推断。'
    )
    result['matched_spec'] = {
        'site_id': '03',
        'plan': name,
        'duration_seconds': duration,
        'quality': payload['quality'],
        'orientation': 'vertical',
        'billing_period': 'per_video',
    }
    return result
