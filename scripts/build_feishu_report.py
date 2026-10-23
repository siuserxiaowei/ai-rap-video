#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the native Feishu release candidate from verified, source-linked records."""
import argparse, collections, datetime, html, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CATEGORIES={'rap':'照片与Rap专站','music_video':'音乐视频','lip_sync':'口型与人物','music':'音乐创作','video':'视频生成','editor':'剪辑与视觉制作'}
def esc(value):return html.escape(str(value),quote=True)
def p(value):return '<p>'+esc(value)+'</p>'
def link(url,label):return '<a href="'+esc(url)+'">'+esc(label)+'</a>'
def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+p(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+p(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
def load(path,default):
    return json.loads(path.read_text()) if path.exists() else default
def shorten(value,limit):
    value=str(value).replace('\n',' ')
    return value if len(value)<=limit else value[:limit-1]+'…'
def build():
    sites=[load(x,{}) for x in sorted((ROOT/'research/sites').glob('*.json'))]
    decisions=load(ROOT/'docs/decisions.json',[])
    codex=[load(x,{}) for x in sorted((ROOT/'research/codex').glob('C[0-9][0-9].json'))]
    gemini=[load(x,{}) for x in sorted((ROOT/'research/gemini').glob('G[0-9][0-9].json'))]
    full=[x for x in sites if x['evidence_status']=='full_page']
    good_gemini=[x for x in gemini if x.get('accepted')]
    verified=load(ROOT/'docs/verification.json',{})
    collection_dates=sorted({x['checked_at'][:10] for x in sites})
    collection_window=' 至 '.join([collection_dates[0],collection_dates[-1]]) if len(collection_dates)>1 else (collection_dates[0] if collection_dates else '未完成')
    title=f'AI Rap Video 网站研究与自主开发方案｜{len(sites)}站 · 100个agent任务 · 50项决策'
    blocks=['<title>'+esc(title)+'</title>','<h1 seq="auto">结论与使用方式</h1>',p(f'本轮采集窗口 {collection_window}。本次目的性检索形成{len(sites)}个不同网站的研究记录，其中{len(full)}站取得有效官方正文。Codex任务验收记录{len(codex)}份，Gemini有效独立会话{len(good_gemini)}个。报告用于选择创作路径和安排开发，不构成生成效果实测排名。'),p('研究发现：照片生成新Rap、替换参考表演人物、为已有歌曲制作视觉，是不同工作流。先确认音频从哪里来、人物数量和最终时长，再比较画质与费用。默认优先验证短片流程与透明规格。'),p('本轮已经实现的功能和测试以文末验收记录为准。真实供应商渲染尚未配置时，工作台明确返回不可用，不把本地brief预览描述成AI视频成片。'),'<h1 seq="auto">研究问题、范围与方法</h1>',p('研究问题：哪些网站能参与AI Rap Video创作，各自需要什么输入、输出什么、如何收费，哪些能力可通过公开API集成，以及这些证据支持怎样的产品路线？'),p('纳入直接Rap专站、音乐视频、音乐创作、口型/人物、通用视频与剪辑平台。候选来自中英文网页检索，再按相邻工作流扩展。按不同主域计站点，同站多页不重复计数。网站数量不等于独立公司的数量；相似模板不证明同一运营方。'),p('采集以官方产品、价格、开发文档为主，经Agent Reach的Jina Reader保存正文；不可达时记录错误并尝试官方其他页面。每条保留URL、采集日期、证据等级、未知项与本地原文。仅搜索摘要、错误页、登录门或挑战页不能算有效全文。'),p('Codex逐站整理和核验；Gemini在同一公开语料上做40个站点分析及10个专题审查，保留不同conversation_id。中文补充检索新增6站，由Codex补充核查，并交原G50继续分析。这是独立分析复核，不是两份独立外部证据。未注册付费、未上传人物照片、未购买视频生成，因此画质、口型、等待时间、成功率和退款履约均未实测。'),table(['证据等级','含义','本次数量'],[['full_page','至少一个相关官方正文有效读取；价格/API仍可能有缺口',len(full)],['partial','取得部分资料，关键页面或信息缺失',sum(x['evidence_status']=='partial' for x in sites)],['inaccessible','未取得有效相关正文',sum(x['evidence_status']=='inaccessible' for x in sites)]]),p('可达性：B站公开搜索已取得案例；YouTube抓取触发登录风控；Twitter、Reddit、小红书暂无已验证可用后端。以上缺口未被计算为有效站点证据。'),'<h1 seq="auto">创作路径与产品机会</h1>',table(['目标','典型路径','对产品的含义'],[['自己或朋友演唱新Rap','照片＋主题／歌词→原创音频与短表演','按单人／双人、场景和用途组织表单'],['替换熟悉表演中的人物','参考视频／模板＋照片→角色替换，可能保留原音','模板音频与原创音频要明确分开'],['为已完成歌曲制作MV','音频→节拍／结构→分镜→镜头→剪辑与字幕','长曲流程需要分镜复核与逐镜头修改'],['精确处理口型','现成视频＋音轨→口型重绘','不能推断会创作歌词或伴奏'],['快速完成社交发布','短片＋字幕＋比例调整→可发布文件','以完整输出规格而非模型列表选型']]),p('上述分流由本次页面观察归纳，属于产品分析。实际用户需求强度尚需访谈或使用数据验证。'),'<p>代表来源：'+link('https://rapvideogenerator.com/','RapVideoGenerator')+'、'+link('https://rapvideo.ai/','RapVideo.ai')+'、'+link('https://tryh3.com/generator/ai-rap-video','TryH3')+'、'+link('https://www.capcut.com/features/ai-rap-video-generator','CapCut')+'</p>','<h1 seq="auto">全部网站比较</h1>',p('以下按研究记录编号排列，不是质量排名。API“已找到文档”只表示通用或相关接口有公开资料，不代表完整Rap流程可集成；具体范围见各站明细。')]
    rows=[]
    for s in sites:
        rows.append([s['id']+' '+s['name'],CATEGORIES.get(s['category'],s['category']),shorten(s['summary'],80),{'documented':'有公开资料，需看覆盖范围','not_found':'本次未发现文档','unknown':'待核'}[s['api']['status']],s['evidence_status']])
    blocks.append(table(['网站','用途','已读页面所述流程','API','正文'],rows))
    blocks+=['<h1 seq="auto">价格与免费边界</h1>',p('先对齐时长、分辨率、音频来源、画幅、实际付款周期和点数规则再比较。不同站的credits不可相加；年付折月不是逐月付款；理论每条均价不等于首次需要支付的金额。以下为官网快照，最终登录报价、税费与地区差异待核。')]
    price_rows=[]
    for s in sites:
        if s['category']=='rap' or s['id'] in ('18','19','28','34'):
            price_rows.append([s['name'],shorten(s['pricing']['summary'],120),shorten(s['pricing']['free_tier'],80),s['pricing'].get('source_url') or s['url']])
    blocks.append(table(['网站','计费观察','免费范围','来源'],price_rows))
    blocks+=['<h1 seq="auto">API集成与开发取舍</h1>',p('优先选择有当前官方文档、鉴权、任务状态与错误约定的接口；消费者网页能够生成不等于允许自动化集成。文档存在不证明Rap、原声、口型或双人模式已被开放。')]
    blocks.append(table(['网站','公开接口证据与范围','文档来源'],[[s['name'],shorten(s['api']['summary'],240),s['api'].get('url') or s['url']] for s in sites if s['api']['status']=='documented']))
    blocks+=['<h1 seq="auto">逐站证据与限制</h1>']
    for s in sites:
        blocks+=['<h2 seq="auto">'+esc(s['id']+' '+s['name'])+'</h2>',p(shorten(s['summary'],120)),p('输入：'+shorten('；'.join(s['inputs']),80)+'。输出：'+shorten('；'.join(s['outputs']),80)+'。'),p('适合：'+shorten(s['best_for'],70)+'。边界：'+shorten('；'.join(s['limitations']),160)),p('价格：'+shorten(s['pricing']['summary'],100)),p('API：'+shorten(s['api']['summary'],120)), '<p>采集：'+esc(s['checked_at'])+'；正文等级：'+esc(s['evidence_status'])+'。来源：'+'；'.join(link(x['url'],shorten(x.get('title') or x['url'],40)) for x in s['sources'] if x['kind']!='secondary')+'</p>']
    blocks+=['<h1 seq="auto">50项产品与技术决策</h1>',p('以下是可审查的决策摘要与验收条件，用于承接50轮评估要求；它们不代表所有建议已实现。每项回链研究编号，原始记录与状态保存在docs/decisions.json。')]
    blocks.append(table(['编号与主题','决策','验收与来源编号'],[[x['id']+' '+x['topic'],x['decision'],x['acceptance']+'（站点'+','.join(x['evidence_site_ids'])+'）'] for x in decisions]))
    blocks+=['<h1 seq="auto">完整开发计划与worktree分工</h1>',p('本轮路线：证据与schema→研究API和导出→研究工作台→创作brief→任务与报价→完整流程测试→独立终审→飞书回读。Codex主线程整合，各功能在独立worktree开发，按指定文件范围提交，验收后回收干净worktree。'),table(['任务','输出','验收'],[['C41 数据契约','目录schema、来源校验、筛选与统计','无效数据给出诊断、来源文件与主域可追溯'],['C42 采集工具','可复现来源抓取与证据索引','错误页不误判、URL和hash可查'],['C43 后端API','受限静态服务、目录与保存接口','真实HTTP往返、路径与请求校验'],['C44 研究工作台','检索、筛选、比较、来源详情','1440/390px和键盘可操作'],['C45 创建流程','solo/duo、场景、规格、歌词与brief','保存、重开、下载，不显示假视频'],['C46 任务系统','持久化任务、幂等与provider边界','重复请求复用、冲突明确、未配置渲染诚实拒绝'],['C47 价格估算','来源支持的规格匹配','不混点数、不将估算当实时价格'],['C48 报告导出','JSON/CSV/Markdown','字段完整、链接保留、CSV公式中和'],['C49 测试与质量','异常、持久化、交互与可访问性检查','验证完整用户路径，修复实际问题'],['C50 独立终审','README、验收清单和剩余工作','不以单测证明未测试的生成能力']]),p('后续真实渲染：根据已确认官方文档实现一个供应商adapter；用授权素材完成快Rap口型、人物一致性、中文、费用、失败重试和退款对账测试；再加入认证、私有存储、队列、监控和正式部署。各步骤有验证门槛，未完成不得标成上线能力。')]
    blocks+=['<h1 seq="auto">本轮验收与执行证据</h1>',p('本地项目：/Users/xiaowei/work/ai-rap-video-20261023。完整计划见PLAN.md；研究契约见RESEARCH_CONTRACT.md；站点记录、原文和两组agent台账在research/。'),p('可运行命令：python3 -m rap_workbench.server --port 8787。默认仅在本机127.0.0.1开放。')]
    if verified:
        blocks.append(p(json.dumps(verified,ensure_ascii=False)))
    else:blocks.append(p('开发验收尚未写入；发布前必须补齐docs/verification.json并回查实际测试结果。'))
    blocks+=['<h1 seq="auto">限制与下一轮验证</h1>',p('样本为目的性检索，不证明市场份额、营收、趋势覆盖或全网穷尽。站点宣传可能更新或互相复制；价格和模型名称在采集后可能变化。没有真实付费生成，本报告不判断成片质量或履约。'),p('下一轮优先核查：价格冲突与登录后报价；公开API是否覆盖Rap所需音频与口型；自带音轨和模板音轨的许可范围；快语速、双人、遮挡与中文的生成质量；真实成本与失败恢复。')]
    return title,'\n'.join(blocks),{'sites':len(sites),'full_page_sites':len(full),'codex_records':len(codex),'gemini_accepted':len(good_gemini),'decisions':len(decisions),'verification_present':bool(verified)}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--draft-path',required=True);parser.add_argument('--allow-incomplete',action='store_true');a=parser.parse_args()
    title,xml,counts=build()
    if not a.allow_incomplete:
        assert counts['full_page_sites']>=30,counts
        assert counts['codex_records']==50 and counts['gemini_accepted']==50 and counts['decisions']==50,counts
        assert counts['verification_present'],counts
    dest=ROOT/a.draft_path
    assert ROOT in dest.resolve().parents
    dest.write_text(xml)
    print(json.dumps({'title':title,'draft_path':str(dest),'counts':counts,'characters':len(xml)},ensure_ascii=False))
