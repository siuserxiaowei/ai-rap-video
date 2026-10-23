"""Source-preserving, offline research exports; all returned strings are UTF-8."""
import csv
from datetime import datetime, timezone
import io
import json

METHOD = '整理已有公开页面研究记录；未在导出时联网、注册、付款或执行生成实测。'
LIMITATIONS = [
    '官网功能、性能和政策属于供应商宣称，不能视作实测结果；适用性与产品决策属于研究推断。',
    '价格为记录核查日期的页面信息，保留原币种、计费周期、积分与附注；未验证结账，不合并跨站积分，不把年付折月价当作单次价格。',
    'API documented 仅表示发现公开文档；not_found 表示本次范围内未发现，unknown 表示未知，两者均不能推断为不提供 API。',
    'full_page 表示取得公开页面证据，不表示完整产品验证；缺失字段标为未记录，不补成免费、可商用或已有 API。',
]
CSV_FIELDS = (
    'generated_at', 'id', 'name', 'url', 'category', 'checked_at',
    'evidence_status', 'summary', 'inputs', 'outputs', 'features',
    'pricing_summary', 'free_tier', 'pricing_plans', 'pricing_source_url',
    'api_status', 'api_summary', 'api_url', 'limitations', 'best_for',
    'source_urls', 'sources', 'observations', 'method', 'report_limitations',
)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def export_json(sites):
    """Keep each original site object, including unknown and extension fields."""
    return json.dumps({'generated_at': _now(), 'method': METHOD,
                       'limitations': LIMITATIONS, 'sites': list(sites)},
                      ensure_ascii=False, allow_nan=False, indent=2) + '\n'


def _cell(value):
    if value is None:
        return ''
    result = _json(value) if isinstance(value, (list, dict)) else str(value)
    # Leading whitespace/control characters can conceal spreadsheet formulas.
    # Prefix the original text (without stripping it) so CSV roundtrips retain it.
    if result.lstrip().startswith(('=', '+', '-', '@')) or result.startswith(('\t', '\r', '\n')):
        result = "'" + result
    return result


def export_csv(sites):
    """One logical CSV row per site; nested data remains parseable JSON."""
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator='\r\n')
    writer.writeheader()
    generated_at = _now()
    for site in sites:
        pricing, api = site.get('pricing') or {}, site.get('api') or {}
        row = {key: site.get(key) for key in CSV_FIELDS}
        row.update(generated_at=generated_at, pricing_summary=pricing.get('summary'),
                   free_tier=pricing.get('free_tier'), pricing_plans=pricing.get('plans'),
                   pricing_source_url=pricing.get('source_url'), api_status=api.get('status'),
                   api_summary=api.get('summary'), api_url=api.get('url'),
                   source_urls=[source.get('url') for source in site.get('sources', [])],
                   method=METHOD, report_limitations=LIMITATIONS)
        writer.writerow({key: _cell(value) for key, value in row.items()})
    return output.getvalue()


def _md(value):
    if value is None or value == '' or value == [] or value == {}:
        return '未记录'
    if not isinstance(value, str):
        value = _json(value)
    value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    for char in ('\\', '`', '*', '_', '[', ']', '#', '|'):
        value = value.replace(char, '\\' + char)
    return value.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


def _items(lines, label, values):
    lines.extend(['', '**' + label + '**'])
    if not values:
        lines.append('- 未记录')
    else:
        lines.extend('- ' + _md(value) for value in values)


def export_markdown(sites, decisions=None):
    """Complete Chinese report with original evidence and decision provenance."""
    sites, decisions = list(sites), list(decisions or [])
    lines = ['# Rap 网站研究报告', '', '生成时间（UTC）：' + _now(), '',
             '## 摘要与研究范围', '',
             '本次导出包含 {} 个站点、{} 项产品决策；范围仅为传入的研究记录，不代表全网排名。'.format(len(sites), len(decisions)),
             '', METHOD, '']
    lines.extend('- ' + text for text in LIMITATIONS)
    dates = sorted({site.get('checked_at') for site in sites if site.get('checked_at')})
    lines.extend(['', '记录核查日期：' + ('、'.join(dates) if dates else '未记录'), '', '## 逐站研究'])
    for site in sites:
        lines.extend(['', '### {} · {}'.format(_md(site.get('id')), _md(site.get('name'))), '',
                      '- 官网：' + _md(site.get('url')),
                      '- 类别：' + _md(site.get('category')),
                      '- 核查日期：' + _md(site.get('checked_at')),
                      '- 证据等级：' + _md(site.get('evidence_status')),
                      '', '**摘要（来源记录，非实测结论）**', '', _md(site.get('summary'))])
        for key, label in [('inputs', '输入'), ('outputs', '输出'), ('features', '功能（公开页面宣称）')]:
            _items(lines, label, site.get(key))
        pricing = site.get('pricing') or {}
        lines.extend(['', '**价格与免费边界**', '',
                      '- 价格摘要：' + _md(pricing.get('summary')),
                      '- 免费范围：' + _md(pricing.get('free_tier')),
                      '- 价格来源：' + _md(pricing.get('source_url'))])
        _items(lines, '套餐原始记录（保留金额、币种、周期、积分与附注）', pricing.get('plans'))
        api = site.get('api') or {}
        lines.extend(['', '**API 证据边界**', '',
                      '- 原始状态：' + _md(api.get('status')),
                      '- 核查说明：' + _md(api.get('summary')),
                      '- 文档或核查入口：' + _md(api.get('url'))])
        _items(lines, '限制与待验证事项', site.get('limitations'))
        lines.extend(['', '**适用性（研究推断）**', '', _md(site.get('best_for'))])
        _items(lines, '观察（研究推断）', site.get('observations'))
        lines.extend(['', '**来源与本地证据**'])
        sources = site.get('sources') or []
        if not sources:
            lines.append('- 未记录')
        for source in sources:
            lines.extend(['- ' + _md(source.get('title')) + '：' + _md(source.get('url')),
                          '  - 类型：' + _md(source.get('kind')),
                          '  - 本地证据：' + _md(source.get('local_path')),
                          '  - 支持范围：' + _md(source.get('supports'))])
    lines.extend(['', '## 产品决策（{} 项）'.format(len(decisions)), '',
                  '以下为产品方向与验收条件，不表示实现状态已完成；状态按原记录保留。'])
    if not decisions:
        lines.extend(['', '未提供决策记录。'])
    names = {'id': '编号', 'topic': '主题', 'decision': '决策', 'rationale_summary': '依据摘要',
             'acceptance': '验收条件', 'status': '记录状态', 'evidence_site_ids': '依据站点编号'}
    by_id = {site.get('id'): site for site in sites}
    for decision in decisions:
        lines.extend(['', '### ' + _md(decision.get('id')) + ' · ' + _md(decision.get('topic'))])
        for key, value in decision.items():
            lines.append('- {}：{}'.format(names.get(key, key), _md(value)))
        for identifier in decision.get('evidence_site_ids', []):
            site = by_id.get(identifier)
            lines.append('- 依据来源（{}）：{}'.format(_md(identifier), _md(site.get('url')) if site else '当前导出范围内未记录'))
    return '\n'.join(lines) + '\n'
