# C44 研究工作台交付复核

## 范围

仅实现 `web/index.html`、`web/styles.css`、`web/app.js`；未改 create 页面、shared 或后端。原生 HTML/CSS/ES module，无外部依赖。依据 WORKBENCH_SPEC、API_WIRE_CONTRACT、DESIGN_NOTES 与已有 MASTER 的蓝灰研究 dashboard 方案，采用系统中文字体、深蓝侧栏与静态 SVG 波形，未采用销售漏斗建议。已读取 ui-ux-pro-max，并查阅 keyboard focus modal 的 UX 结果与 quick-reference 的可访问性、触控、性能规则。

## 真实 API 接线

- 目录使用 GET /api/sites 的 q、category、evidence_status、api_status；筛选为 AND 关系，搜索 300ms 防抖，取消旧请求避免覆盖新结果。
- 概况使用 GET /api/stats 的动态 total、full_page、by_api、by_category、checked_at，未硬编码站点总数。
- 来源明细读取 GET /api/sites/<id>；展示来源链接、支持范围、归档路径、核查日期、输入输出、价格、API 范围、限制与研究推断。
- 比较最多 3 站，选择跨筛选保留，可清空；逐站比较输出、免费额度、计费与能力边界，无实测排名。
- JSON / CSV / Markdown 使用 GET /api/report，成功后下载原始响应；非 2xx 显示服务端真实错误并可点击重试。
- 创建入口指向 /create.html；C45 负责独立创建页。

## 两站信息关系复核

1. **RapVideoGenerator（01）**：免费 10 credits 与最低视频 100 credits 表明“免费歌曲体验”不能写成“免费视频”。年付折月价、分辨率每秒 credits、套餐权限并列，不能折成一个虚构单次价格。因此卡片保留价格边界，详情同时展示免费额度与限制；“已读正文”与“官网宣称 / 未实测”分层展示。
2. **Udio（35）**：歌曲生成与站内分享不能等同文件下载或完整 Rap MV 输出；当前研究记录明确下载停用，授权亦待核。因此比较把“输出”“限制与待核”“API 范围”作为独立信息块；来源明细保留下载变更帮助页与失效条款页的说明，不以订阅或历史品牌认知推导当前能力。卡片中 API not_found 表示本次核查结论，documented 统一称“有接口资料”，并显示原记录的能力范围，不称完整 Rap API。

## 安全与交互静态复核

所有第三方字段使用 textContent / createElement，未使用 innerHTML、outerHTML 或 insertAdjacentHTML。外链仅允许合法 HTTPS、无用户名密码；新窗口带 noopener noreferrer。原生 dialog 提供关闭按钮、Escape、背景点击关闭和触发控件焦点恢复；浏览器原生模态焦点约束。显式表单标签、焦点环、44px 控件、live 状态、跳转主内容和 reduced-motion。390px 媒体查询改为顶部导航、双列概况、单列目录和单列比较；仍需真实浏览器复核。

## 已执行验证（2026-10-24）

`node --check web/app.js` 通过；`git diff --check` 通过；静态搜索未发现 HTML 字符串注入方法或远程资源依赖。

启动独立 `python3 -m rap_workbench.server --port 8844`，Python urllib 读取实际 HTTP：

| 请求 | 结果 |
| --- | --- |
| GET /api/stats | 200，251 bytes，total=38 |
| GET /api/sites?category=rap | 200，65938 bytes，total=38，filtered=13 |
| GET /api/sites?q=zzzz_no_match | 200，41 bytes，total=38，filtered=0 |
| GET /api/sites/35 | 200，5821 bytes |
| GET / | 200，6299 bytes（添加导出错误区前的读取） |
| GET /styles.css | 200，12093 bytes（导出错误样式添加前） |
| GET /app.js | 200，10251 bytes（导出处理添加前） |
| GET /api/report?format=json | 503，导出模块尚未集成，未伪造成功 |

最终修改后重新读取静态文件：`/` 200 / 6369 bytes，`/styles.css` 200 / 12338 bytes，`/app.js` 200 / 11346 bytes；8844 服务已停止。

## 待根线程集成验收

CUA getState 返回 browsers=[]，native Google Chrome 可用。按根线程安排，未操作共享 Chrome；桌面与 390px 真实布局、点击筛选、三站上限、对话框键盘和焦点恢复、下载文件内容、brief 入口往返交由根线程在完整集成版本统一验收。HTTP 输出不冒充浏览器交互通过。CSV/Markdown 下载需要导出模块集成后复核。

8844 测试服务在交付前停止；测试生成的独立 .workbench 运行数据不进入提交。
