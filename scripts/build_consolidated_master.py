#!/usr/bin/env python3
# coding: utf-8
"""Build the source-backed unified Feishu master and its Markdown mirror."""

import copy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts/consolidation-20261024'
TITLE = 'AI Rap Video 调研与开发交付总纲（合并校验版）'
MASTER = 'https://vi8r050ecuz.feishu.cn/docx/YzORdyPJroCrXZxCoBKceiZ3nUb'
LEGACY = 'https://vi8r050ecuz.feishu.cn/docx/AQqCdG2Q3ogetUxgdFxcwKFgnah'
VERIFIED = 'https://vi8r050ecuz.feishu.cn/docx/TiqGd7dHWoAqBex3KCvcnzpVnKc'
REPO = 'https://github.com/siuserxiaowei/ai-rap-video'
PUBLIC_SHA = '4e37d762037196df2eb044d0240ec8b602b44b67'
LOCAL_SHA = 'f0623e8325b7975a931b41f93949d272fc179c03'
CATEGORIES = {'rap':'Rap与照片专站','music_video':'音乐视频','lip_sync':'口型与人物',
              'music':'音乐创作','video':'通用视频','editor':'剪辑与视觉制作'}
STATES = {'verified':'按引用证据验证','implemented_pending_browser':'已实现，浏览器待验',
          'planned_next_stage':'下一阶段', 'partially_implemented_live_pending':'部分实现，真实供应商待验',
          'implemented_contract_tested_live_pending':'契约实现已测，真实供应商待验'}


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def source(name):
    value = read('artifacts/consolidation-20261024/' + name)
    assert value['ok']
    doc = value['data']['document']
    return doc, ET.fromstring('<root>' + doc['content'] + '</root>')


def key(url):
    part = urlsplit(url)
    host = (part.hostname or '').lower().removeprefix('www.')
    if host == 'synclabs.so':
        host = 'sync.so'  # Official introduction and captured301 redirect agree.
    if host == 'github.com':
        return 'repo:' + '/'.join(part.path.strip('/').split('/')[:2]).lower().removesuffix('.git')
    return 'site:' + host


def link(url, label):
    node = ET.Element('a', {'href':url})
    node.text = label
    return node


def inline(node, value):
    parts = value if isinstance(value, (list, tuple)) else [value]
    for item in parts:
        if isinstance(item, ET.Element):
            node.append(copy.deepcopy(item))
        else:
            text = str(item)
            if len(node):
                node[-1].tail = (node[-1].tail or '') + text
            else:
                node.text = (node.text or '') + text


class Document:
    def __init__(self):
        self.root = ET.Element('root')
        ET.SubElement(self.root, 'title').text = TITLE

    def heading(self, value, level=1):
        ET.SubElement(self.root, 'h' + str(level), {'seq':'auto'}).text = value

    def p(self, value):
        inline(ET.SubElement(self.root, 'p'), value)

    def table(self, headers, rows):
        table = ET.SubElement(self.root, 'table')
        head = ET.SubElement(ET.SubElement(table, 'thead'), 'tr')
        for value in headers:
            inline(ET.SubElement(ET.SubElement(head, 'th'), 'p'), value)
        body = ET.SubElement(table, 'tbody')
        for values in rows:
            assert len(values) == len(headers)
            row = ET.SubElement(body, 'tr')
            for value in values:
                inline(ET.SubElement(ET.SubElement(row, 'td'), 'p'), value)

    def code(self, value, language='bash'):
        ET.SubElement(ET.SubElement(self.root, 'pre', {'lang':language}), 'code').text = value


PURPOSES = {
 'rapchat.com':'录音、歌词辅助与移动制作工作流', 'lyricstudio.net':'歌词与押韵辅助',
 'soundverse.ai':'音乐生成与音轨组织', 'neume.io':'原稿归入伴奏类，产品身份与Rap关联待核',
 'boomy.com':'编曲与发行工作流', 'soundful.com':'伴奏与分轨用途，授权范围待核',
 'loudly.com':'配乐与循环片段工作流', 'beatoven.ai':'情绪配乐与段落组织',
 'somio.ai':'原稿归入伴奏类，当前产品与能力待核',
 'manus.im':'通用创作自动化线索，不能确认为独立Rap生成服务',
 'acestudio.ai':'歌声合成与编辑工作站线索', 'kits.ai':'音色与声音处理工具线索',
 'weights.gg':'社区模型与音色资源线索', 'uberduck.ai':'文本到歌声/说唱工作流线索',
 'ultimatevocalremover.com':'人声与伴奏分离工作流线索',
 'omnihuman1.org':'音频驱动人物/全身生成研究线索',
 'humanaigc.github.io':'音频驱动人像研究线索', 'viggle.ai':'参考动作与角色运动迁移线索',
 'noisee.ai':'音乐可视化与MV组织线索', 'airmusic.ai':'音乐相关创作/发布线索，当前定位待核',
 'atlabs.ai':'叙事视频与分镜组织线索',
}
REPO_PURPOSES = {
 'openvpi/diffsinger':'歌声合成研究与部署线索',
 'rvc-boss/gpt-sovits':'声音合成与说话人适配线索',
 'rvc-project/retrieval-based-voice-conversion-webui':'声音转换工作流线索',
 'kwaivgi/liveportrait':'肖像动作迁移线索', 'antgroup/echomimic':'音频/条件驱动人像线索',
 'fudan-generative-vision/hallo':'音频驱动肖像与长时处理线索',
 'zhenglinzhou/aniportrait':'音频与姿态引导人像线索', 'opentalker/sadtalker':'音频驱动肖像线索',
 'rudrabha/wav2lip':'对口型基线与变体核查线索', 'tencent/mimicmotion':'人体动作迁移研究线索',
 'fudan-generative-vision/champ':'姿态条件人物视频研究线索',
}


def neutral(url):
    canonical = key(url)
    if canonical.startswith('repo:'):
        return REPO_PURPOSES[canonical[5:]]
    return PURPOSES[canonical[5:]]


def markdown(root, mermaid, image_url):
    def text(value):
        value = html.escape(value or '', quote=False)
        return re.sub(r'([\\`*\[\]|])', r'\\\1', value)

    def rich(node):
        if node.tag == 'a':
            value = '[' + ''.join(rich_content(node)) + '](<' + node.get('href') + '>)'
            return value
        return ''.join(rich_content(node))

    def rich_content(node):
        yield text(node.text)
        for child in node:
            yield rich(child)
            yield text(child.tail)

    blocks = []
    for node in root:
        if node.tag == 'title':
            blocks.append('# ' + rich(node))
        elif re.fullmatch(r'h[1-6]', node.tag):
            blocks.append('#' * (int(node.tag[1]) + 1) + ' ' + rich(node))
        elif node.tag == 'p':
            blocks.append(rich(node))
        elif node.tag == 'pre':
            blocks.append('```' + node.get('lang', '') + '\n' + ''.join(node.itertext()) + '\n```')
        elif node.tag == 'table':
            rows = []
            for row in node.iter('tr'):
                rows.append('| ' + ' | '.join(rich(cell).replace('\n', '<br>') for cell in row) + ' |')
            rows.insert(1, '| ' + ' | '.join('---' for _ in list(next(node.iter('tr')))) + ' |')
            blocks.append('\n'.join(rows))
        elif node.tag == 'whiteboard':
            blocks.append('```mermaid\n' + mermaid + '\n```')
        elif node.tag == 'img':
            blocks.append('[实际字幕采样图](<' + image_url + '>)')
        else:
            raise ValueError('Unmapped Markdown block: ' + node.tag)
    return '\n\n'.join(blocks) + '\n'


def build():
    old, old_tree = source('source-master.json')
    eco, eco_tree = source('source-42-research.json')
    proven, proven_tree = source('source-46-research.json')
    sites = [read(str(p.relative_to(ROOT))) for p in sorted((ROOT/'research/sites').glob('*.json'))]
    decisions = read('docs/decisions.json')
    assert len(sites) == 46 and len(decisions) == 50
    by_key = {key(site['url']):site for site in sites}
    entries = read('artifacts/consolidation-20261024/legacy-entries.json')
    union = {}
    for entry in entries:
        item = union.setdefault(key(entry['url']), dict(entry, origins=[], aliases=[]))
        if entry['source'] not in item['origins']: item['origins'].append(entry['source'])
        if entry['name'] not in item['aliases']: item['aliases'].append(entry['name'])
    assert len(union) == 43
    overlaps = [item for canonical,item in union.items() if canonical in by_key]
    extras = [item for canonical,item in union.items() if canonical not in by_key]
    assert len(overlaps) == 11 and len(extras) == 32
    for index,item in enumerate(extras, 1): item['candidate_id'] = f'B{index:02d}'
    board = next(eco_tree.iter('whiteboard'))
    diagram = ''.join(board.itertext())
    image = next(proven_tree.iter('img'))
    diagram_url = LEGACY + '#' + board.get('id')
    image_url = VERIFIED + '#' + image.get('id')
    d = Document()
    d.heading('统一摘要与版本口径')
    d.p('本页合并原总纲、42项生态详本、46站出处研究与后续工程验收，并核对公开GitHub。此后以本页作为统一阅读入口。合并日期：2026-10-24；价格、功能与模型仍以各条原始采集日期为准，不把材料合并当作重新生成实测。')
    d.table(['项目','统一口径'], [
        ['研究索引','78条去重入口/项目记录＝46条已建出处记录＋32条未独立核验候选；不是已验证78站。'],
        ['46站证据','42 full_page、4 partial；160个既有市场源文件。full_page表示相关官网正文已读，不表示生成质量、付款或下载通过。'],
        ['旧42/43差异','42详本实际42条；旧总纲实际43条，多出Manus。两份并集43，与46目录重叠11，额外候选32。'],
        ['决策与任务','50条D01–D50；50个不同Codex任务交付，其中48完整验收、C44/C45待浏览器；50个成功独立Gemini会话。后续复用原agent，不新增计数。'],
        ['本地最新验收','529 passed，441引擎＋88工作台；393个subtests另记，0失败/错误/跳过。此为既有本地日志，本次合并未重跑。'],
        ['真实已测输出','程序化短视频、实际ASS中文字幕样本、两种全高清画幅与完整解码；没有生成AI人声、人物动画或口型。'],
        ['公开与本地','公开main仍4e37d76旧快照；本地f0623e8包含后续新工作台/Sync/字幕能力，尚未在所核对公开main中出现。'],
        ['当前门槛','真实浏览器的桌面/390px/键盘/下载仍未验收；真实供应商质量、下载与费用阶段仍需配置和样本。']])
    d.p(['公开代码入口：',link(REPO, 'siuserxiaowei/ai-rap-video'),'；当前已核对的公开提交：',link(REPO+'/commit/'+PUBLIC_SHA,'4e37d76'),'。不要将之后的本地529项结果归到这个公开旧提交。'])
    d.table(['来源或版本','内容与证据范围'], [
        [[link(MASTER,'原总纲／本统一入口'),'（合并前revision '+str(old['revision_id'])+'）'],'保留仓库入口、43项生态线索、六项工程机制与旧版运行说明，按当前证据修订措辞。'],
        [[link(LEGACY,'42项生态详本'),'（源revision '+str(eco['revision_id'])+'）'],'补充声音/开源人物/动作研究与原生架构图；旧稿性能与许可主张不作为本轮验证。'],
        [[link(VERIFIED,'46站与开发验收来源'),'（源revision '+str(proven['revision_id'])+'）'],'46站逐条出处、价格/API/限制、50决策以及Sync、预览与字幕分阶段验收。'],
        [[link(REPO+'/tree/'+PUBLIC_SHA,'公开代码 '+PUBLIC_SHA[:7])],'494个文件、37份site JSON、旧airap与早期目录模块；162个测试定义可数，只有8项目录测试原始日志，未找到完整162运行或公开CI证据。'],
        ['本地已验收 f0623e8','529原始日志与受测文件哈希匹配；其应用/测试与受测基线de7871e一致。文档提交本身不代表重新跑测试，也不表示已推送。']])
    d.heading('生态分层与创作路径')
    d.p('两组材料共同覆盖歌词与音乐、声音处理、人物与口型、姿态动作、音乐视觉、通用视频和剪辑。先区分原创Rap、模板换人、已有歌曲做MV与现成视频对口型，再选择工具；这些路径不能只用模型名称混为一类。')
    d.table(['路径','输入与目标','核查重点'], [
        ['新Rap短片','主题/歌词＋形象→音乐与视频','音乐是否新生成、人物数量、时长、音轨权利与失败规则'],
        ['替换参考表演人物','模板/参考视频＋照片→角色替换','是否保留原音、模板使用边界与人物一致性'],
        ['已有歌曲制作MV','音频→结构/分镜→镜头→剪辑与字幕','分段修改、长曲一致性与最终输出规格'],
        ['口型处理','现成视频＋音轨→口型重绘','不预设接口会创作歌词/伴奏，快Rap质量另行验收'],
        ['音乐视觉与发布','音频/短片＋画幅/字幕/音效','抽象视觉与人物演唱分开，文件导出与链接分享分开']])
    d.heading('46条有出处研究记录：比较、价格与API')
    d.p('以下是按独立主域建立的研究样本，按编号排列，非质量排名。所有官网效果属于供应商宣称；API documented只表示找到相关公开资料，覆盖范围逐条核对。完整输入、输出、限制及来源在文末46条档案。')
    d.table(['编号与名称','类别','入口','页面所述流程','证据/API'], [[s['id']+' '+s['name'],CATEGORIES[s['category']],link(s['url'],'官网/产品页'),s['summary'],s['evidence_status']+' / '+s['api']['status']] for s in sites])
    d.p('计费比较先对齐时长、分辨率、音频来源、画幅、付款周期及积分规则。各站credits不相加；年付折月不等于逐月付款，免费静图/歌曲/预览也不等于可下载视频。以下为采集快照，不是结账金额或本系统成本。')
    priced = [s for s in sites if s['category']=='rap' or s['id'] in ('18','19','28','34')]
    d.table(['网站','计费观察','免费范围','原来源'], [[s['id']+' '+s['name'],s['pricing']['summary'],s['pricing']['free_tier'],link(s['pricing'].get('source_url') or s['url'],'价格来源')] for s in priced])
    d.table(['网站','公开接口范围与限制','文档'], [[s['id']+' '+s['name'],s['api']['summary'],link(s['api'].get('url') or s['url'],'接口来源')] for s in sites if s['api']['status']=='documented'])
    d.p('重叠产品采用现有出处记录：旧Hedra价格不能覆盖当前独立API钱包；Udio下载限制不以旧稿高音质评价替代；未找到官方公开API不能由第三方接口补成官方。完整限制保留在各站档案。')
    d.heading('32条补充候选与11条旧名映射')
    d.p('这一批继承旧生态稿的研究方向，保留原链接与GitHub仓库路径，尚未独立核对当前功能、可用性、API、价格、模型或使用许可。它们没有因合并自动成为新增已核查网站。Neume、Somio和Manus的产品身份或专用Rap定位尤其需要再核。')
    d.table(['候选','原稿名称/别名','原入口','待核用途方向','出处'], [[e['candidate_id'],'；'.join(e['aliases']),link(e['url'],'原稿入口'),neutral(e['url']),'42详本＋旧总纲' if 'legacy_42' in e['origins'] else '旧总纲新增Manus'] for e in extras])
    d.p('两份旧稿的其余11项已经包含在46目录，作为别名映射保留。SyncLabs官方旧入口本次返回301到sync.so，现有官方introduction正文也自称Sync Labs，因此合并到28号；这不证明其任何性能或实时性主张。')
    d.table(['旧稿名称/别名','旧入口','统一研究记录'], [['；'.join(e['aliases']),link(e['url'],'旧入口'),by_key[key(e['url'])]['id']+' '+by_key[key(e['url'])]['name']] for e in overlaps])
    d.p('去重使用普通站点主机名与明确别名；GitHub按owner/repo保留11个不同仓库。Hallo/Hallo2和Wav2Lip/Wav2Lip-HD各按给定的一条仓库入口计，不据名字拆成已验证的多个版本。代码、权重、数据与素材的使用条件仍需分别核对。')
    d.heading('工程架构、算法机制与原目标蓝图')
    d.p('工程由研究工作台和独立airap本地合成路径组成。旧稿六项机制保留为模块能力描述：808合成、运动数据滤波、姿态数学、分小节镜头调度、节拍特效和逐词字幕；它们不能一起推导出已完成AI人物演唱。')
    d.table(['模块','当前实现或用途','验收边界'], [
        ['rap_workbench / web','研究检索、比较、来源、导出；SQLite brief、文字分镜、历史价格参考','HTTP与数据已测，桌面/390px交互与浏览器下载待验。网页provider_render仍503。'],
        ['airap/lyrics','中英音节/词、韵律与小节时间规划，保留全部有效歌词','规则分析，不是已接入AI歌词创作。最多64KiB UTF-8、40–300BPM、本地预览120秒；上限不等于全时长压力验收。'],
        ['airap/audio','wave/struct/math合成808、snare、hi-hat；节拍/瞬态数值与规则对齐','合成器乐或提供音频；规则对齐不是读取真实语音的强制对齐，mock/分离适配器不是专业分离模型质量证明。'],
        ['airap/avatar','12类视素映射、CoArticulationFilter、HeadBobber四元数/点头状态','规划数据；MockLipSyncRenderer状态没有进入最终画面，人物图片当前明确拒绝。没有140BPM真实口型效果基准。'],
        ['airap/subtitles','KineticSubtitleBuilder逐词厘秒标签、押韵强调、ASS/SRT','已验证所选实际中文字幕烧录与帧时序；厘秒参数不等于通用实测音画误差，字体名仍为请求。'],
        ['airap/director','4/8-Bar等乐句边界调度，Zoom/Shake/Glitch滤镜规划','真实双色源片切点样本为24fps第6帧/0.25秒；其他切点受帧率量化。'],
        ['airap/compositor','FFmpeg多轨道合成、每cut裁剪、流/尺寸/FPS/实测时长校验、原子替换','失败保留旧输出。完整解码在所列样本执行，不宣称每个未来输出都已人工观看。'],
        ['pipeline / CLI','preview首选，generate兼容；显式工具与字幕模式；缺失媒体拒绝','procedural_placeholder、未生成AI人声/口型，主题仅requested，未应用到视觉。'],
        ['Sync客户端 / journal / CLI','REST create/get/estimate、原请求与幂等键持久化、本地plan/show、门禁GET refresh','默认不联网，CLI无submit；本机契约服务器不是真实供应商质量、下载或账单验证。']])
    d.p(['下面保留',link(diagram_url,'42详本的原架构画板'),'。它是目标蓝图，含尚未交付的SVS、人像/LoRA和4K节点；各节点的当前状态以紧随其后的表格为准。'])
    # Resource cloning failed on the deployed writer. Replay the unchanged
    # source Mermaid instead, and verify its hash and native rendered output.
    ET.SubElement(d.root,'whiteboard',{'type':'mermaid'}).text = diagram
    mapping = [
        ['A1','主题/歌词提示词','已有文字输入；AI歌词生成未接入'],['A2','BPM/调性参考','BPM与beat grid已有；自动调性分析/应用未验'],['A3','Character Sheet','规划；当前人物图片拒绝'],
        ['B1','Rhyme/Syllable/Bars','规则分析与调度已有；新词生成未接入'],['B2','伴奏/分轨','合成节拍/提供音频已有；专业生成与分轨质量未验'],['B3','SVS/Flow-Guided TTS','未接入、未生成'],['B4','UVR5＋Beat/Onset','数值与mock/适配层；不能视为真实UVR5已验'],
        ['C1','Multi-View LoRA','规划，未训练/渲染'],['C2','Scene Prompts per Bar','brief、模板分镜与cut已有；语义画面生成未验'],['C3','背景/B-roll','当前程序图案，theme_applied=false'],
        ['D1','Phoneme-to-Viseme','规则估计与规划，非真实语音强制对齐'],['D2','LivePortrait/EchoMimic/Wav2Lip渲染','尚未挂载进最终视频'],['D3','Pose/Motion Guidance','规划与数学状态，未渲染人物表演'],
        ['E1','节拍裁剪/拼接','已测所列切点，仍受FPS量化'],['E2','Shake/Glitch/Zoom','滤镜路径存在，未做通用审美/人物质量验收'],['E3','动力学字幕','所选中文字幕实际烧录通过'],['E4','最终文件/4K/画幅','只实测两种1080p方向的短样本；4K为未验证目标']]
    d.table(['原图节点','保留的目标','当前状态'],mapping)
    d.table(['旧稿路线','保留的组织方式','仍需验收'],[
        ['一键平台','低步骤创作/灵感演示路线','速度、角色一致性、文件输出逐产品实测'],['人物口型','特写镜头单独选择口型/人物方案','快Rap、多人、遮挡、中文音画质量'],['动作迁移','参考动作与中景表演分层','肢体/服饰/身份一致性，不能假定消除所有伪影'],['音频响应视觉','音频视觉与人物演唱分开设计','节拍对齐与真实图像控制范围'],['开源组合','ComfyUI、歌声、人像、分离模块可作为研究方向','许可、模型安装、显存/延迟与维护成本逐项验证；未部署']])
    d.heading('50项产品与技术决策')
    d.p('这是D01–D50可审查的结论、依据和验收条件，承接50轮评估要求；不是声称50项建议全部实现。状态来自当前docs/decisions.json，引用编号对应46站档案。')
    d.table(['编号/主题','结论与依据摘要','验收条件','当前状态','来源站点'],[[x['id']+' '+x['topic'],x['decision']+'。'+x['rationale_summary'],x['acceptance'],STATES.get(x['status'],x['status']),','.join(x['evidence_site_ids'])] for x in decisions])
    d.heading('并行开发、验收与回收记录')
    d.p('先有PLAN和契约，再按文件边界在独立worktree提交、整合、复核。原50个Codex任务与50个独立Gemini会话保留原始台账，不把后续复用算作新50个。C44/C45未做真实浏览器验收，仍不记完整通过，原两个干净worktree保留。')
    d.table(['阶段','工作与交付','验收/回收'],[
        ['最初研究/功能','C01–C40网站研究；C41–C50数据、采集、API、目录UI、创建、任务、报价、导出与复核','50交付；48完整验收，C44/C45待验'],['Sync迭代','复用C48客户端/C49提交记录/C50本地CLI，保存官方协议','工作台88项含本机HTTP契约；3树回收，无供应商调用'],['引擎修复','复用三agent修输入回退/歌词截断/镜头裁剪/假成功与文件校验','合并387项；两画幅程序化视频解码；3树回收'],['字幕迭代','复用三agent作模式/工具/字体与真实ASS路径','合并529项、7真实ASS路径、4全高清CLI、3中文帧；3树回收'],['本次资料合并','三位旧agent只读复核覆盖、公开版本和声明；主线程整合发布','不改产品代码、旧任务登记或供应商/UI验收状态']])
    d.heading('测试证据、实际字幕图与版本边界')
    d.table(['结果','实际范围','证据口径'],[
        ['旧162','154个引擎＋8个早期目录测试定义','旧稿162 passed/2.96s缺对应完整原始公开日志；公开只找到8项日志。未找到Actions/Checks成功证据，不能称CI已过。'],
        ['后续154复测','继承六份引擎模块在本地154 passed/2.49s','baseline-tests.txt；不能冒充旧162那次原始运行。'],['首版54 / Sync88','研究工作台、HTTP、SQLite、导出及Sync本机契约','历史阶段/子集，不与后来总数累计。'],['引擎合并387','299引擎＋88工作台','程序化媒体与切点检查；当时默认工具没有ASS，字幕未烧录。'],['最新本地529','441引擎＋88工作台；393子测试另记','529 passed in13.29s、0失败/错误/跳过，原始日志与受测代码哈希一致；本次合并只核对既有证据。']])
    d.p('本地证据：artifacts/iterations/subtitle-burnin-20261024/final-tests.txt、real-caption-smoke.json和toolchain-build.json；受测应用基线de7871e，随后f0623e8的应用/测试未变。公开main仍4e37d76，因此不能把529及新模块当成公开旧代码的通过记录。')
    d.p('实际中文事件为0.25–0.75秒；同源视频字幕开/关在0.1/0.5/0.9秒差异为0/2996/0像素。主线程查看受控、竖屏、横屏三个0.5秒样本，“中文烧录预览”可辨；四次全高清CLI覆盖required/auto/off，均1秒、30fps且完整音视频解码。只对这些样本作此结论，字体面匹配、所有帧与所有文字排版未独立验证。')
    ET.SubElement(d.root,'img',{'src':image.get('src'),'width':'640','height':'360'})
    d.p(['上图为真实视频解码帧，',link(image_url,'原采样图与验收出处'),'。它不证明AI人物演唱或网页交互通过。'])
    d.p('项目内FFmpeg8.1.1/libass0.17.5由校验过的源码构建，实际有ASS，原全局FFmpeg路径和哈希保持一致；新装pkgconf及libunibreak。二进制、字体与生成媒体不在Git内，复制源码不等于拥有该本机工具链。')
    d.heading('分版本启动与复现指南')
    d.p('公开旧版：可克隆固定4e37d76检查历史源码。本次没有推送代码；其旧CLI只有generate/version，不能运行新preview参数或完整工作台。旧成功文案不构成AI人声/口型证明。')
    d.code('git clone https://github.com/siuserxiaowei/ai-rap-video.git\ncd ai-rap-video\ngit checkout 4e37d762037196df2eb044d0240ec8b602b44b67\n# Python3.10+、pytest、FFmpeg/FFprobe准备好后，历史入口为：\npython3 -m pytest -q\npython3 -m airap.cli generate --lyrics examples/sample_lyrics.txt --bpm 130 --output legacy-preview.mp4')
    d.p('下列新命令只适用于本机已验收f0623e8工作区，或以后确实发布并核对过的新版本；新克隆的当前公开main不包含这些文件。工作台仅绑定本机，8788已有本项目服务时直接访问；新实例另选空闲端口。')
    d.code('cd /Users/xiaowei/work/ai-rap-video-20261023\n.venv/bin/python -m rap_workbench.server --port 8788\n# 浏览研究与brief： http://127.0.0.1:8788/ 和 /create.html')
    d.p('实际字幕预览需要已构建的本机ASS工具与已安装字体。preview是程序化合成；generate为兼容别名。显式缺失音频/工具报错，图片输入暂不支持，主题只作请求记录；默认PATH工具仍可能没有ASS。')
    d.code('.venv/bin/python -m airap.cli preview \\\n  --lyrics "中文烧录预览" --bpm 240 --aspect 9:16 \\\n  --ffmpeg .workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg \\\n  --ffprobe .workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe \\\n  --subtitle-mode required --subtitle-font "Arial Unicode MS" \\\n  --output subtitle-preview.mp4 --output-dir output --json')
    d.p('复现完整529项须有新源码、测试和ASS工具链，并设置下列测试变量；否则7个可选真实ASS用例会跳过。当前应用最低Python3.10+，构建助手另需Python3.12+，归档验收环境为Python3.15。构建配方与版本哈希见docs/iterations/subtitle-burnin-20261024/TOOLCHAIN.md。')
    d.code('AIRAP_TEST_FFMPEG="$PWD/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg" \\\nAIRAP_TEST_FFPROBE="$PWD/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe" \\\n.venv/bin/python -m pytest -q')
    d.p('Sync命令行仅plan/show和有门禁的GET refresh；没有提交生成功能。refresh还需已知远端ID、--allow-network、RAP_ENABLE_SYNC_CLIENT=1与环境中的专用SYNC_API_KEY。费用预估使用填写时长，不证明真实计费时长或硬预算。')
    d.heading('下一阶段路线与未关闭验收')
    d.table(['阶段','工作','关闭条件'],[
        ['现有必要验收','C44/C45实际桌面、390px、键盘焦点与浏览器下载','需要允许访问的浏览器环境；当前页面访问策略终止过会话，未用替代工具绕过。'],['真实供应商','专用配置、授权样本、真实请求/媒体回读与下载','中文快Rap、双人/遮挡、人物一致性、延迟、实际费用与失败对账，均不能由本机契约代替。'],['补充研究','对32线索核当前官网/仓库、模型、许可与部署','取得相关一手资料后再升级证据等级；不把线索数量当完成量。'],['扩展架构','ComfyUI节点、LivePortrait/其他人物渲染、角色LoRA、私有存储/队列/监控','这些保留为规划；逐项验证模型权利、运行资源与端到端输出，不预称工业级。'],['公开同步','将适合公开的后续版本审查后发布到现有仓库','实际推送/远端树和日志回读后再更新公开版本行；本次只做资料合并。']])
    d.p('当前真实供应商生成和付费生成为0，本地程序化视频及所选字幕样本已测；整体产品验收仍未完成。文档整合不改变这些状态，不把GitHub公开、代码存在、单测通过或媒体帧查看互相替代。')
    d.heading('附录A：46站逐条证据与限制')
    for site in sites:
        d.heading(site['id']+' '+site['name'],2)
        d.p([link(site['url'],site['url']),'；类别：'+CATEGORIES[site['category']]+'；采集：'+site['checked_at']+'；正文：'+site['evidence_status']])
        d.p(site['summary'])
        d.p('输入：'+'；'.join(site['inputs'])+'。输出：'+'；'.join(site['outputs']))
        d.p('页面所述功能：'+'；'.join(site['features']))
        d.p('价格：'+site['pricing']['summary']+'；免费范围：'+site['pricing']['free_tier'])
        d.p('API：'+site['api']['status']+'；'+site['api']['summary'])
        d.p('适用场景（研究推断）：'+site['best_for']+'；限制：'+'；'.join(site['limitations']))
        refs = ['原始来源：']
        for index,item in enumerate(site['sources']):
            if index: refs.append('；')
            refs.extend([link(item['url'],item.get('title') or item['url']),'（'+item['kind']+'）'])
        d.p(refs)
        if site.get('observations'): d.p('研究附注：'+'；'.join(site['observations']))
    d.heading('附录B：来源、证据与合并记录')
    d.p(['旧生态详本：',link(LEGACY,'42项资料与原画板'),'；完整研究/历次验收来源：',link(VERIFIED,'46站来源文档'),'；公开代码：',link(REPO,'GitHub仓库'),'。原总纲和两个来源的合并前完整XML快照保存在artifacts/consolidation-20261024/。'])
    d.p('本次资料覆盖、版本和声明由三位旧agent只读交叉复核；原task注册表和站点JSON未修改。新统一口径为46条出处记录＋32条候选、50决策；162/529按版本与证据等级分别记载。没有重新执行历史162/当前529，也没有进行远端代码推送。')
    used = {n.get('href') for n in d.root.iter('a')}
    previous = {}
    for node in proven_tree.iter('a'):
        if node.get('href'): previous.setdefault(node.get('href'), ''.join(node.itertext()) or node.get('href'))
    missing = [(url,label) for url,label in previous.items() if url not in used]
    if missing:
        d.p('以下接口/工具链等参考来自46站来源文档的后续验收章节，合并时完整保留：')
        d.table(['参考','链接'],[[label,link(url,url)] for url,label in missing])
    body = '\n'.join(ET.tostring(n,encoding='unicode') for n in list(d.root)[1:])
    full = ET.tostring(d.root[0],encoding='unicode') + '\n' + body
    ART.mkdir(parents=True,exist_ok=True)
    (ART/'consolidated-master.xml').write_text(full,encoding='utf-8')
    (ART/'consolidated-body.xml').write_text(body,encoding='utf-8')
    md = markdown(d.root,diagram,image_url)
    (ART/'consolidated-master.md').write_text(md,encoding='utf-8')
    (ROOT/'MASTER_FEISHU_DOC.md').write_text(md,encoding='utf-8')
    facts = {'title':TITLE,'master_document_id':'YzORdyPJroCrXZxCoBKceiZ3nUb',
             'generated_at':datetime.now(timezone.utc).isoformat(),'verified_sites':46,'full_page_sites':42,
             'legacy_union':43,'legacy_overlaps':11,'supplemental_unverified_candidates':32,'combined_index':78,
             'decision_rows':50,'public_sha':PUBLIC_SHA,'local_accepted_sha':LOCAL_SHA,'test_snapshot':529,
             'whiteboard_source_token':board.get('token'),'whiteboard_mermaid_sha256':hashlib.sha256(diagram.encode()).hexdigest(),
             'image_source_token':image.get('src'),'prior_reference_urls':sorted(previous),
             'supplemental_candidates':extras,'overlap_map':[{'legacy':e['name'],'url':e['url'],'site_id':by_key[key(e['url'])]['id']} for e in overlaps],
             'xml_sha256':hashlib.sha256(full.encode()).hexdigest(),'body_sha256':hashlib.sha256(body.encode()).hexdigest()}
    assert {e['url'] for e in union.values()} <= {n.get('href') for n in d.root.iter('a')}
    assert set(previous) <= {n.get('href') for n in d.root.iter('a')}
    (ART/'consolidation-manifest.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:facts[k] for k in ('verified_sites','supplemental_unverified_candidates','combined_index','decision_rows','test_snapshot')},ensure_ascii=False))


if __name__ == '__main__':
    build()
