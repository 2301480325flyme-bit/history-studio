"""Refresh physical-file purposes. No moves/deletes; skip junctions and dependencies."""
from pathlib import Path
from collections import Counter
import json, hashlib, re, os, ast
from datetime import date

ROOT=Path(r'D:\history\codx_3 history studio'); CTL=ROOT/'00_管理'
proof=json.loads((CTL/'migration-verification.json').read_text(encoding='utf-8'))
prior={str(Path(r['destination'])).lower():r for r in proof['records']}
adapted={str(Path(r['path'])).lower() for r in json.loads((CTL/'path-adaptation.json').read_text(encoding='utf-8'))}
ADAPT_COUNT=len(adapted)
ae_before_path=CTL/'ae-dependencies-before.json'
before=json.loads(ae_before_path.read_text(encoding='utf-8')) if ae_before_path.is_file() else {}
# Before report may be raw bridge result or plain dependency object.
if 'footage' not in before and 'result' in before: before=before['result']
tiles={Path(x['path']).name:x['path'] for x in before.get('footage',[]) if x['path'].startswith('C:')}
literature={}
litindex=ROOT/'06_报告/资料审阅/historical-materials/魏晋南北朝文献索引.json'
for entry in json.loads(litindex.read_text(encoding='utf-8')):
 literature[f"lit-{entry['id']:02}"]=Path(entry['path']).name
DYNAMIC={'文件用途清单.csv','文件用途说明.md','00_管理/inventory-data.json','00_管理/inventory-summary.json'}
CORE={
 'studio_catalog.py':('查询/校验/导出按年份和快照组织的古城位置与关系记录；未知归属明确返回未知','城池与事件数据','当前主链；数据仍待补全'),
 'studio_geolayers.jsx':('GEOlayers经纬度锚点及人物旗、路线等AE叠加组件；不替代疆界数据或Finalize','GEOlayers与AE构建','当前主链技术组件'),
 'geolayers_jobs.py':('向已打开工程提交GEOlayers任务、记录回执和超时；防止项目误用及异步队列重复提交','GEOlayers任务调度','当前主链；异步完成闭环未通过'),
 'compile.py':('将director配置编译为ae-job.json、run.jsx及静态地图素材；用于旧视觉基准与过渡','编译构建','静态地图过渡工具'),
 'build.jsx':('AE矢量模板：城池、人物旗、箭头、字幕、运镜与动作库；原输出配置须另行适配','AE工程构建','旧主链模板，可复用组件'),
 'compile_script.py':('把规范导演Markdown解析校验并转换为director配置；不能自动证明史料正确或保证无重叠','导演分镜编译','过渡编译工具'),
 'run.py':('组织旧AE工程构建及分块渲染；aep-only供工程预览；不是GEOlayers接入已完成的证明','构建与导出','旧主链可恢复导出工具'),
 'chunk_render.py':('短时间范围分块渲染AVI，再编码、校验、缓存和拼接；保留失败续做能力','渲染导出','旧链导出兜底'),
 'resume_encode.py':('续接已生成的渲染片段编码工作，减少重复渲染','渲染导出','旧链恢复工具'),
 'mimo_tts.py':('通过MiMo API生成旁白音频，读取环境变量密钥；音色参数与文本控制配音','配音制作','配音工具；H风格为已认可方向'),
 'place_lookup.py':('旧版地名定位查询，结合curated位置为导演配置提供坐标','城池定位','过渡工具；新关系查询优先studio_catalog'),
 'historical_places.json':('候选古城与坐标来源登记；现有城址不能视为已核准的精确点位','城池与事件数据','当前主链数据；城址待核'),
 'historical_relations.json':('按时间和证据记录驻军/归属等关系；行政、名义政权、控制与封地不得互相推断','城池与事件数据','当前关系库，尚未完整'),
 'places_curated.json':('旧定位整理表，为既有样片生成坐标；需与新catalog核对后复用','城池定位','旧定位参考'),
 'ACTION_LIBRARY.md':('城池等级及death/ascend/depose等通用动作的参数说明','动作规范','AE组件参考'),
 'SCRIPT_FORMAT_v1.md':('导演Markdown语法、字段与分幕约束；供AI写分镜和编译器读取','导演分镜','现有规范，需结合GEOlayers适配'),
 'GEOlayers3历史Studio实施大纲.md':('GEOlayers优先制作主链、城池规范、建设阶段及验收门槛','Studio规划','当前实施大纲；真实进度见根目录思路与方向'),
 'test_studio_geolayers.py':('GEOlayers组件的已有自动检查代码；文件存在不表示本轮已执行','代码质量','保留检查工具；本轮未运行'),
 'studio.py':('History Studio编译器/CLI：episode.yaml查库校验、逐句配音实测、底图拼接、分区构建与Remotion渲染','Remotion Studio','当前主链；2026-10-07建立'),
 'SCRIPT.md':('History Studio脚本格式（episode.yaml v1）：拍、地点、镜头、元素与箭头性质约束','Remotion Studio','当前脚本规范'),
 'Episode.tsx':('History Studio通用Remotion合成：读取episode.json，镜头、底图、河网、疆域与各层叠加','Remotion Studio','当前通用渲染引擎'),
 'Marks.tsx':('History Studio地图标记：城池标签避让、竖旗、发光箭头、战事、印章、说明卡','Remotion Studio','当前通用渲染组件'),
 'Overlays.tsx':('History Studio屏幕版式：片名、阶段标、年份牌、字幕条、图例、底注、肖像切入、大标题','Remotion Studio','当前通用渲染组件'),
 'anim.ts':('History Studio缓动、镜头插值与箭头路径采样工具','Remotion Studio','当前通用渲染组件'),
 'palette.py':('History Studio政权色板生成与校验：OKLCH统一亮度、色盲模拟、邻接分色','Remotion Studio','当前配色系统'),
 'regions.py':('多政权疆域快照处理：按名分组、邻接计算、自动配色、标签锚点、繁转简','Remotion Studio','当前疆域层工具'),
 'palette.json':('16色位政权色板及校验结果（fill/muted/edge/flag）','Remotion Studio','当前色板数据'),
 'FONTS.md':('History Studio字体清单与开源商用许可说明','Remotion Studio','字体许可记录'),
 'basemap_dem.py':('可商用底图：ETOPO 2022晕渲+Natural Earth海陆湖河，参考片式灰陆深海','Remotion Studio','当前底图生成器'),
 'cells.py':('郡格子：县治/郡治种子在地形代价网格上扩张，追踪郡/州多边形（示意范围）','Remotion Studio','当前疆域底座'),
 'territory.py':('势力时间轴编译：州郡归属展开、校验、按状态溶解轮廓与标签','Remotion Studio','当前疆域层'),
 'Territory.tsx':('Remotion疆域层：逐郡染色扩散、势力轮廓、州郡名与势力标签、斜纹','Remotion Studio','当前通用渲染组件'),
 'parse_junguozhi.py':('解析维基文库《后汉书·郡国志》为州-郡-县结构','Remotion Studio','东汉郡格子数据源'),
 'fetch_han_wikidata.py':('Wikidata精确名称批量查询东汉郡县候选坐标（CC0）','Remotion Studio','东汉郡格子数据源'),
 'fetch_modern_seats.py':('郡治今址对照表的Wikidata坐标定位','Remotion Studio','东汉郡格子数据源'),
 'match_han.py':('以郡治为锚校验并选择县治坐标','Remotion Studio','东汉郡格子数据源'),
 'han-140.geojson':('东汉105郡/13州推算范围（郡界为示意）','Remotion Studio','当前郡格子'),
 'server.py':('History Studio网页工作台本地服务：剧集导入/配置/校验/构建/渲染/预览API与文件服务（仅127.0.0.1）','Remotion Studio','当前网页工作台'),
 'index.html':('History Studio网页工作台前端单页：剧集列表、配置表单、脚本编辑、分拍、任务、成片、资料工具','Remotion Studio','当前网页工作台'),
 '启动 History Studio.bat':('双击启动网页工作台并打开浏览器','Remotion Studio','日常入口'),
 'build_sanguo_places.py':('三国数据包：45处三国关键地点批量从Wikidata(CC0)取坐标入共享地名库','Remotion Studio','三国系列数据'),
 'people-三国.yaml':('三国人物表片段（立绘路径与封号），供episode.yaml的people引用','Remotion Studio','三国系列数据'),
 'gazetteer.json':('History Studio共享地名库：各集由agent/编辑查证入库的地点，含坐标来源、精度与复核状态','Remotion Studio','当前共享数据；agent条目待人工复核'),
 'SKILL.md':('Agent技能说明：history-video一句话出片工作流、旁白风格、史实红线与自检交付标准','Remotion Studio','当前agent工作规范'),
 'review.md':('History Studio构建审稿单：旁白与原文对照、地点精度、箭头性质、ASR校对与警告','Remotion Studio','每次构建自动生成，供人工审稿'),
 'asr-report.md':('MiMo ASR逐句听写与原稿比对报告；不一致处需真人试听','配音制作','配音自动校对证据'),
 'episode.yaml':('History Studio单集脚本：旁白分拍、地点、镜头与画面元素；经studio.py校验后渲染','Remotion Studio','单集制作输入'),
 'prepare_migration.py':('一次性选择迁移范围并记录源文件SHA-256；移动后不能按原假设重跑','文件管理','本次迁移工具，勿重复执行'),
 'move_files.ps1':('一次性执行已审定的移动计划并创建兼容Junction；非日常整理命令','文件管理','已执行82次移动，勿重复运行'),
 'verify_migration.py':('记录移动完成时原文件与目标文件SHA-256比较；路径适配后的修改另记','文件管理','一次性原字节校验，已通过'),
 'adapt_paths.py':('一次性将P0参数及主链文档中的旧绝对路径适配新位置','文件管理','已执行，变更见path-adaptation.json'),
 'inventory.py':('按物理文件刷新用途说明Markdown及CSV数据；跳过Junction和运行时依赖','文件管理','日常清单维护入口'),
 'build_inventory.mjs':('用artifact-tool组织用途表并导出UTF-8 BOM CSV；读取inventory-data.json','文件管理','CSV生成入口'),
 'migration-plan.json':('原迁移选择、移动动作、新旧路径及源哈希的冻结计划','文件管理','迁移证据，勿覆盖'),
 'migration-verification.json':('2327个原文件移动前后SHA-256逐项一致的冻结证据','文件管理','移动校验通过；后续适配另记'),
 'move-log.jsonl':('实际82次移动和创建Junction的逐操作日志','文件管理','迁移证据'),
 'path-adaptation.json':('迁移后文件/工程路径适配的前后哈希与原因','文件管理','合法内容变更记录'),
 'ae-dependencies-before.json':('迁移前打开P0工程的22项素材路径快照','文件管理','AE依赖来源证据'),
 'ae-dependencies-after.json':('迁移后P0的22项素材路径与存在状态；全部指向新目录','文件管理','当前工程依赖检查通过'),
 'inventory-data.json':('用途表结构化中间数据，供CSV和Markdown生成','文件管理','动态生成，不做自身哈希'),
 'inventory-summary.json':('文件数、分区大小、来源及覆盖校验统计','文件管理','动态生成，不做自身哈希'),
}
SIDECAR={'.shp':'空间几何主文件','.dbf':'与几何逐行对应的属性表','.shx':'几何记录索引','.prj':'坐标参考系定义','.cpg':'属性文字编码声明','.sbn':'空间索引','.sbx':'空间索引配套文件','.qix':'空间查询索引'}
DOCS={
 'AE_EXECUTOR_CODEX_PROMPT.md':'AE执行代理的操作、回执及验收要求',
 'AE_SCRIPT_CODEX_PROMPT.md':'脚本生成代理的AE字段及实现要求',
 'DIRECTOR_PROMPT.md':'将历史题材转换为旁白和分幕导演配置的提示模板',
 'MIMO_TTS.md':'MiMo配音调用与音色/文本配置使用说明',
 'TOPIC_TO_AE.md':'从选题与导演输入生成AE工程的旧制作入口说明',
 'ASSET_EVALUATION.md':'已有地图和素材的适用性、问题及复用建议',
 'COURSE_REVIEW.md':'教程方法与当前生产链的对应评估',
 'EIGHT_PRINCES_PRODUCTION.md':'八王之乱各稿和配音母本的制作进度说明',
 'GEOlayers3-local-data-trial.md':'本地历史地理资料接入GEOlayers的试用证据与缺口',
 'STUDIO建设与制作主链大纲.md':'Studio整体主链规划及新GEOlayers大纲入口',
 'VOICE_PROFILE.md':'声音参考的句子节奏、重音和讲述语气分析',
 'BUILD-INSTRUCTIONS.md':'该版本脚本构建与AE执行说明',
 'READY-TO-RENDER.md':'该版本待渲染步骤清单；不是成功渲染证据',
 'V14-REVIEW.md':'V14视觉审阅问题及后续调整依据',
 'V14-UPGRADE-SUMMARY.md':'V14代码与配置升级总结；预期收益不作为验收结论',
 'INTEGRATION-STATUS.md':'GEOlayers过渡接入工程的实际状态与未完成项',
 'HANDOFF.md':'该阶段交接、输入输出和后续动作说明',
 'SOURCE.md':'同目录数据/素材/对照图的来源与用途记录',
 'BUILD-STATUS.md':'该阶段构建结果、阻塞与回执记录',
 '迁移说明.md':'本次迁入范围、旧区归档、Junction及清单维护方法',
}
def fallback(p,rel):
 name=p.name; stem=p.stem; ext=p.suffix.lower(); stage='资料归档'; state='用途待按内容复核'
 basis='按文件名、目录与格式推定，未逐内容核验'; advice='复用前核实来源、年代和适用条件'
 if '/font-tools/' in rel:
  use=f'fontTools依赖组件「{rel.split("/font-tools/",1)[1]}」：字体子集、字形及格式处理的配套程序/数据；保留旧字体生成链'
  stage='字体处理依赖'; state='第三方依赖，不是Studio业务代码'
  if ext=='.py':
   try:
    doc=ast.get_docstring(ast.parse(p.read_text(encoding='utf-8-sig')))
    if doc: use+='；模块说明：'+re.sub(r'\s+',' ',doc)[:160]; basis='依赖目录及源码模块文档字符串'
   except (ValueError,SyntaxError,OSError,UnicodeError): pass
 elif ext=='.md':
  use=DOCS.get(name,'')
  if not use:
   try:
    text=p.read_text(encoding='utf-8-sig')[:10000]; titles=re.findall(r'^#{1,3}\s+(.+)',text,re.M)
    use='文档「'+(titles[0] if titles else stem)+'」：'+('；'.join(titles[1:4]) if len(titles)>1 else '同目录制作/研究方法与进度说明')
    basis='读取Markdown标题和章节名称；未据此确认功能完成'
   except (OSError,UnicodeError): use=f'文档「{stem}」：同目录制作/研究说明'
  stage='制作规范/报告'; state='阶段文档；当前状态以根目录思路与方向为准'
 elif ext in {'.py','.jsx','.ps1','.mjs','.js'}:
  roles={'prepare':'准备项目输入与基础素材','continue':'继续既有构建步骤','revise':'修订既有导演/项目配置','qa':'收集样片审阅证据','cache_proof':'记录缓存复用证据','build_eight_princes_base':'准备八王之乱底图及基础数据','prepare_eight_princes_v1':'准备旧八王之乱初版输入','run_story':'组织旧多章剧情制作','sapi_tts':'通过Windows SAPI生成过渡配音','check_coverage':'读取疆域范围检查覆盖','check_world300':'检查300年世界疆域数据','extract_jin_291_306':'提取291—306年西晋候选疆域','extract_jin_300':'提取300年西晋候选疆域','inspect-stamp':'读取印章图层与属性作审阅','diagnose-menu':'排查AE扩展或菜单命令','build_map_catalog':'生成地图资料目录索引'}
  use=f'脚本「{name}」：'+roles.get(stem,('构建或渲染指定旧版本输入' if re.match(r'(build|render)_v\d+',stem) else '同目录制作/诊断步骤，执行前核工程与输入'))
  if ext=='.py':
   try:
    doc=ast.get_docstring(ast.parse(p.read_text(encoding='utf-8-sig')))
    if doc: use+='；源码说明：'+re.sub(r'\s+',' ',doc)[:160]; basis='文件名及源码模块文档字符串'
   except (ValueError,SyntaxError,OSError,UnicodeError): pass
  stage='制作工具'; state='保留旧制作工具；本轮未执行'
 elif ext in {'.json','.geojson'}:
  role=''
  if 'director' in name: role='该题材/版本的旁白、人物、镜头与路线输入参数'
  elif name=='project.json': role='项目身份、输入与输出目录、制作参数'
  elif 'phrase-timeline' in name: role='旁白短句时间轴，供人物/字幕/动作对齐'
  elif 'shots' in name: role='分镜时间和画面组织参数'
  elif 'asr' in name: role='参考声音转写及时间片段，供节奏分析；需核转写错误'
  elif 'chunk' in name: role='这一渲染片段的时间范围、编码/校验与缓存元数据'
  elif 'manifest' in name.lower(): role='同目录资产、交付或字体信息溯源清单'
  elif 'metadata' in name: role='该生成物的时长、编码或制作信息'
  elif 'dependencies' in name: role='AE工程引用素材及缺失状态记录'
  elif 'probe' in name or 'preflight' in name: role='运行前环境/接口探测回执'
  elif 'preservation' in name: role='旧版本保留与一致性记录'
  else: role='同目录结构化配置/运行回执'
  use=f'「{name}」：{role}'
  try:
   obj=json.loads(p.read_text(encoding='utf-8-sig'))
   if isinstance(obj,dict): use+='；顶层字段：'+','.join(list(obj)[:8])
   elif isinstance(obj,list): use+=f'；{len(obj)}条记录'
   basis='读取JSON顶层结构及文件名；不据此确认运行成功'
  except (ValueError,OSError,UnicodeError): pass
  stage='制作配置/证据'; state='阶段数据；非最终完成证明'
 elif ext in {'.png','.jpg','.jpeg','.webp'}:
  if name=='land.png': use='陆地分区/底色图，作为旧静态底图工程的地图依赖'
  elif name=='sea.png': use='海洋分区/底色图，与land.png共同组成旧静态地图'
  elif name=='fill.png': use='该年份/政权的疆域填色图，供AE色块叠加'
  elif name=='outline.png': use='该年份/政权的边界线图，与fill.png配套叠加'
  elif name=='terrain.png': use='已有地形底图图像，用于旧静态地图层；放大清晰度需单独审阅'
  elif 'contact' in stem or 'overview' in stem: use='多帧拼图：对比同目录样片/教程的整体节奏和构图'
  elif 'crop' in stem: use='局部放大审阅图：核对同目录旗帜、文字、印章或画质问题'
  elif '/visuals/' in rel: use=f'教程抽帧「{name}」：对应上级教程/模块的画面证据，供学习复刻'
  else: use=f'画面证据「{name}」：记录同目录案例/样片某时间点的构图、标签、人物或运镜'
  stage='素材依赖/视觉证据'; state='图像资产或抽帧参考，非最终史实证据'
 elif ext in {'.wav','.mp3','.flac','.m4a'}:
  use=f'音频「{name}」：'+('对应编号的旁白段，供测句长、停顿及音画校时' if 'narration' in name else '声音参考/语气分析或同目录配音产物')
  stage='配音与校时'; state='声音资料；整片采用需按试听决定'
 elif ext in {'.mp4','.mov','.mkv','.avi'}:
  if 'chunk-' in name: use=f'渲染片段「{name}」：供失败恢复和同编码拼接，非独立成片'; advice='完成整片验收后可按缓存策略清理，现保留可恢复依赖'
  elif name=='ae-av.mkv': use='旧AE渲染片段拼接后的中间音画容器，供后续编码'; advice='最终输出通过后可再生成清理，现保留'
  else: use=f'视频「{name}」：同目录题材/版本的样片或画面输出，用于视觉对照和验收'
  stage='渲染输出'; state='旧生成物，非新GEOlayers主链最终成片'
 elif ext=='.pdf': use=f'文献「{stem}」：研究同目录历史问题、行政沿革或制作方法；引用须回原页核对'; stage='历史研究/制作参考'; state='文献资料，未逐页校勘'
 elif ext=='.aep': use=f'AE工程「{name}」：同目录样片结构和动画；保存重开需保持素材依赖'; stage='AE工程'; state='旧工程/备份；非新主链已验收产物'
 elif ext=='.log' or '日志' in rel:
  use=f'执行日志「{name}」：定位同目录AE构建、渲染或编码阶段报错，保留时间与操作证据'; stage='执行证据'; state='历史运行日志，不是素材'
 elif ext=='.txt':
  if name=='concat.txt': use='FFmpeg拼接输入片段顺序表；配套chunk媒体，不是旁白'
  elif 'narration' in name: use='该题材/版本旁白台词文本；供内容审核与配音输入'
  elif 'finalize' in name: use='GEOlayers Finalize调用状态/诊断文本；超时不代表完成'
  elif 'LICENSE' in name.upper() or 'OFL' in name.upper(): use='同组字体/依赖的许可条款文本，供复用条件核对'
  else: use=f'文本记录「{name}」：同目录资料、构建或分析的说明/证据'
  stage='台词/执行记录'; state='文本资料，具体内容与当时任务核对'
 elif ext in {'.csv','.tsv'}: use=f'表格「{name}」：同目录文件、音频、帧图或研究数据的逐行索引'; stage='索引/审阅证据'; state='历史阶段台账，当前文件用途表另在根目录'
 elif name=='.gitignore': use='版本控制忽略规则，排除生成物/缓存、密钥和仅保留本地的资料'; stage='版本管理'; state='当前Git忽略规则'
 elif name=='.gitattributes': use='Git文本换行规则及图片、音频、字体等二进制素材的Git LFS规则'; stage='版本管理'; state='当前Git LFS配置'
 elif name=='GITHUB.md': use='GitHub仓库收录范围、Git LFS、同步与新电脑恢复说明'; stage='版本管理'; state='当前版本管理说明'
 else: use=f'配套文件「{name}」：同目录资料/工程的辅助依赖，保留原组以便后续复用'
 return use,stage,state,basis,advice
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()
def walk(base):
 for ent in os.scandir(base):
  p=Path(ent.path)
  if ent.is_symlink() or p.lstat().st_file_attributes & 0x400: continue
  if ent.is_dir(follow_symlinks=False):
   if ent.name not in {'node_modules','.git','__pycache__','.venv'}: yield from walk(p)
  elif ent.is_file(follow_symlinks=False): yield p
def purpose(p,rel,previous):
 name=p.name; ext=p.suffix.lower(); stem=p.stem
 use=previous.get('具体作用',''); stage=previous.get('工作流阶段',''); state=previous.get('使用状态','')
 basis=previous.get('用途依据',''); advice=previous.get('管理建议',''); group=''; era=''
 if not use:
  use,stage,state,basis,advice=fallback(p,rel)
 if rel.startswith('00_管理/协作/'):
  stage='三角色协作接入'; state='技术接入记录；不代表历史视频验收'
  basis='2026-10-04授权的LangGraph/Agent Mail接入及文件在协议中的角色'
  advice='邮件由Agent Mail维护；任务状态从checkpoint导出；冻结版本不覆盖'
  if '/mail-archive/' in rel:
   use='Agent Mail上游生成的'+('角色身份档案（不含注册token）' if name=='profile.json' else '邮件/线程Markdown存档；保存角色实际通信和交接')
  elif name in {'checkpoints.sqlite','checkpoints.sqlite-wal','checkpoints.sqlite-shm'}:
   use='LangGraph SQLite任务状态与待发邮件checkpoint；重启以此恢复，不手改'; state='运行时动态文件；本清单哈希仅是采样时快照'
  elif '/runtime/agent-mail/' in rel:
   use='Agent Mail本地服务'+('数据库/事务日志，保存消息、身份与索引' if '.sqlite3' in name else '启动/服务运行记录（文本已避免注册token）'); state='运行时动态文件；本清单哈希仅是采样时快照'
  elif '/builds/' in rel:
   use='协作接入的冻结构建快照/清单：'+name+'；保留版本、输入与证据用于独立复审'
  elif '/reviews/' in rel:
   use='独立Reviewer的冻结审查报告/证据：'+name+'；绑定构建版本和验收条件'
  elif name=='task.json': use='任务可读导出，真实状态由LangGraph checkpoint管理'
  elif name=='events.jsonl': use='从checkpoint导出的状态转移；不代替Agent Mail交流记录'
  elif name=='roles.json': use='稳定邮箱与当前宿主子代理的公开映射；不保存注册密钥'
  elif 'handoff' in name: use='该角色的接手、结果、未决问题与下一步交接记录'
  elif '/evidence/' in rel: use='本次接入的服务/技能/代码实际验证证据：'+name
  elif name=='history_runner.py': use='LangGraph任务CLI：冻结验收、有限返修、checkpoint恢复及Agent Mail消息补发'
  elif name=='test_runner.py': use='运行器的真实子进程恢复与验收门槛测试；HTTP边界使用协议模拟服务'
  elif name=='start-agent-mail.ps1': use='检查并启动本地Agent Mail服务；绑定127.0.0.1，保留数据库及Markdown存档'
  elif name=='bootstrap-identities.py': use='确保同一项目三个稳定邮箱；私有注册token保存在工作区外'
  elif name=='verify-installation.py': use='只读核实本地服务、邮箱、Markdown存档、MCP配置和技能，输出新版本证据'
  else: use='三角色接入的说明、要求或测试记录：'+name
  return use,stage,state,basis,group,era,advice
 if name in CORE:
  use,stage,state=CORE[name]; basis='主链接口、既有审阅与本次迁移操作记录'; advice='保留依赖；修改后更新清单与状态'
 if '/code-before/' in rel:
  use='旧代码快照：'+use; state='历史诊断参考，不作为当前入口'
 if ext in SIDECAR:
  group=str(p.parent.relative_to(ROOT)/stem).replace('\\','/')
  use=f'{stem}：{SIDECAR[ext]}；与同名SHP组整体使用，不能单独拆走或按同名判重复'
  stage='GIS数据准备'; state=previous.get('使用状态','空间原始资料；年份/坐标系/许可待按说明核实'); basis=basis or 'SHP格式角色与同名文件配套关系'
  advice='保留同名shp/shx/dbf及prj/cpg等配套；历史归属另查年份证据'
 elif name.endswith('.shp.xml'):
  group=str(p.parent.relative_to(ROOT)/name[:-8]).replace('\\','/'); use=f'{name[:-8]}：SHP元数据说明，核对来源、字段、坐标系'; stage='GIS数据准备'
 elif ext=='.geojson':
  try:
   obj=json.loads(p.read_text(encoding='utf-8-sig')); fs=obj.get('features',[])
   types=','.join(sorted({str((x.get('geometry') or {}).get('type','空')) for x in fs}))
   use+=f'；结构读取：{len(fs)}个要素，几何类型{types or "未声明"}'
   basis+='；本轮只核结构，不证明疆域精度或控制归属'
  except (ValueError,OSError): basis+='；本轮结构未读通'
  stage='GIS/历史疆域或城址'; group=rel
 if '/历史地图集/' in rel:
  use=f'历史地图集图页「{p.parent.name}/{name}」：核查地名、河流、道路与断代疆域；适合作参考而非精确GIS'; stage='历史地理研究'; state='图册参考；引用与图页年代需核'; basis=previous.get('用途依据','图册路径和图页文件名，未逐图校勘')
 if '/史料文献/' in rel:
  use=previous.get('具体作用',f'史料文本「{stem}」：检索人物、纪年、地名与事件，供旁白和事件关系互证'); stage='史料研究'; state=previous.get('使用状态','文本研究参考；版本与原文待核')
 match=re.search(r'lit-\d{2}',name)
 if match and match.group() in literature:
  title=literature[match.group()]; use=f'「{title}」的'+('抽取文本：检索研究观点，空文本可能是扫描版，回原PDF查页码' if ext=='.txt' else f'审阅衍生文件{name}：定位原文图页/抽样证据'); stage='文献研究证据'; basis='魏晋南北朝文献索引.json明确对应原PDF'; state='研究辅助，不替代原著校核'
 if '/GEOlayers瓦片依赖/' in rel:
  use=f'{name}：P0工程实际引用的Esri底图瓦片，已从AE缓存复制供工程找回素材；不是高清底图全集'; stage='AE工程依赖'; state='当前已重链接；现代文字与放大模糊仍在'; basis='迁移前后AE FootageItem依赖及复制哈希'; advice='与P0工程保留；瓦片公开使用条件需核'
 if '/geolayers-p0/' in rel:
  stage='GEOlayers接入P0'
  if name=='probe.json': use='当前P0工程GEOlayers同步接口探测任务；预期工程路径防误操作'
  elif name=='draw.json': use='P0城址GeoJSON绘制请求；异步绘制完成尚未通过，勿重复堆队列'
  elif name.startswith('finalize-'): use='P0底图Finalize请求范围参数；回调闭环尚未通过，不能据此宣称离线完成'
  elif name=='places.geojson': use='由城池库导出的洛阳/邺城候选点，供P0定位；近似城址待核'
  elif name=='build-p0.jsx': use='从V15模板构建12秒P0地理镜头；已有P0时拒绝重复新建'
  elif name=='add-overlays.jsx': use='给已存在P0添加经纬度锚定人物旗、文字和示意箭头；不自动绘制历史疆界'
  elif name=='resume-partial-build.jsx': use='按当时工程ID续接半成品构建的一次性脚本；不能作为通用重建入口'
  elif ext=='.aep': use='当前12秒P0工程：地图定位、旗帜、箭头与地理运镜技术样板；22项素材已迁入'; state='可打开技术预览；Finalize未通过，非V14重制成片'
  elif ext in {'.png','.jpg','.jpeg','.mp4'}: use=f'P0技术预览{name}：记录城址锚点/箭头/运镜效果，底图仍有现代标注和模糊'; state='技术预览，未通过最终视觉验收'
 if rel.startswith('01_工作流/projects/') and re.search(r'director-v(?:[1-9]|1[0-3])(?:\D|$)',name):
  state='早期导演配置保留供剧情/参数追溯；非当前GEOlayers生产入口'
 if name=='director-v14.json':
  use='V14导演配置：燕尾旗、政权字、相机等旧视觉基准，供GEOlayers重制转换'; stage='导演配置'; state='静态地图基准，非GEOlayers正式版'
 if name=='ae-job.json': use='该版本编译后的AE参数、素材路径和输出设置；供run.jsx读取与问题追溯'; stage='AE生成配置'; state='生成物，不表示已渲染验收'
 if name=='run.jsx': use='该版本编译生成的AE执行脚本，创建图层/动画/渲染队列；修改输入后重新编译'; stage='AE生成脚本'; state='生成物；成片状态另看实际工程及验收'
 if name=='source-manifest.json': use='该版本素材来源、引用和构建溯源清单；用于复用依赖与追责，不证明最终验收'; stage='构建证据'
 if '/eight-princes-pilot-001-v14/' in rel:
  state='V14旧视觉基准；原地图可用于对比，非GEOlayers重制最终成果'
  if ext=='.aep': use='V14八王之乱71秒AE视觉基准工程，作为旗帜/动作/剧情参数参考'
 if '/eight-princes-pilot-001-v15-geolayers/' in rel: state='GEOlayers过渡工程；完整重制和Finalize尚未验收'
 if '/eight-princes-sima-yan-v2-pauses/' in rel: state='完整版旧暂停调整母本/生成物，待新GEOlayers主链重做验收'
 if '/voice-auditions/' in rel:
  stage='配音方向选择'; use=f'配音试听「{name}」：对照节奏、重音和句间停顿；保留参数/文字与音频对应'; state='试听资料；H获用户认可，其他不自动作为整片定稿'
 if '/配音参考/' in rel or '/声音风格参考/' in rel:
  stage='声音参考'; state='用户声明有真人声音授权；本库未存授权文件，未独立核验'
 if ext in {'.ttf','.otf','.woff','.woff2'}: use=previous.get('具体作用',f'字体「{stem}」：供宋体/文化感标签及旁白字幕排版；具体许可看同组说明'); stage='文字视觉素材'; group=str(p.parent.relative_to(ROOT)).replace('\\','/')
 if name in {'OFL.txt','LICENSE','LICENSE.md','LICENSE.txt'}: use=f'{p.parent.name}授权条款：决定同组字体/数据/项目可否复用；不能推及其他资料'; stage='来源与许可'; state='随原资料保存，使用前阅读'
 if ext in {'.aep','.aepx','.prproj'} and '参考工程' in rel:
  use=previous.get('具体作用',f'参考工程「{name}」：研究地图合成、标签与运镜结构；可能依赖插件、字体、缓存'); stage='AE结构参考'; state='参考工程；依赖和使用权须核'
 if rel.startswith('04_参考/'):
  stage='教程/视觉参考'
  if ext in {'.mp4','.mov','.mkv','.avi'}: use=previous.get('具体作用',f'教程/案例「{stem}」：学习地图底图、地名、箭头、人物、运镜或制作步骤；从题目定位内容'); state='参考学习；不作为直接发布成片'
  elif name=='ANALYSIS.md': use='三条目标视频的视觉拆解和AE复刻建议，按色块、路线、人物、字幕、镜头整理'; state='已做视觉拆解；不证明原作者软件或史实'
  elif name=='TIMELINE.md': use='三条参考视频逐时间点画面观察，供导演节奏和信息密度对照'; state='抽帧观察，不含已完成语音转写'
 if rel.startswith('06_报告/'):
  state=previous.get('使用状态','历史阶段报告/审阅证据；以根目录方向文档为当前状态')
  if name=='历史资料分析与选题索引.md': use='23个GeoJSON、26组SHP、压缩包与33份文献的用途/问题索引，作为选择素材入口'; stage='资料研究导航'
 if ext in {'.zip','.rar','.7z'}: group=rel; advice=advice or '保留原包及说明；不是全部可直接导入AE，按组解压筛选，不执行未知安装包'
 if rel in DYNAMIC:
  use={'文件用途清单.csv':'所有物理文件的用途、状态、来源、新旧路径及SHA-256总表','文件用途说明.md':'全部物理文件按功能逐项说明，供人工导航','00_管理/inventory-data.json':'用途表结构化中间数据','00_管理/inventory-summary.json':'用途表数量、大小及校验汇总'}[rel]
  stage='文件管理'; state='动态生成，避免递归自身哈希'; basis='本次实际文件盘点与既有审阅'; advice='运行inventory.py及build_inventory.mjs刷新'
 if rel=='README.md': use='新Studio总导航、功能目录、当前工程及城池查询入口'; stage='工作区导航'; state='当前入口'; basis='本次整理与项目实际状态'
 if rel=='思路与方向.md': use='汇总历史内容目标、GEOlayers优先主链、数据规范、真实缺口和下一步阶段'; stage='Studio规划'; state='当前方向与进度'; basis='用户要求、本地代码/工程与接入证据'
 if rel.startswith('03_素材/人物立绘/'):
  registry=ROOT/'03_素材/人物立绘/三国立绘/people-三国.yaml'
  people={Path(image).name:person.strip() for person,image in re.findall(r'^\s+([^#\n:]+):\s*\{image:\s*([^,}]+)',registry.read_text(encoding='utf-8-sig'),re.M)}
  if name in people:
   use=f'三国人物「{people[name]}」透明立绘：用于人物发言、登场和关系展示；身份、史料与设计边界见同系列人物卡'
   stage='人物视觉素材'; state='现行登记立绘；进入具体剧集前核对人物时期与服饰'; basis='people-三国.yaml、系列README与人物卡'
  elif '/对照/' in rel:
   use='三国立绘生成来源与像素检查记录' if '制作检查' in name else '三国立绘对照图：检查透明边缘及人物在小尺寸下的区分'
   stage='人物视觉素材审阅'; state='素材检查记录；不代表实际剧集合成验收'; basis='系列README与人物卡'
 if rel.startswith('03_素材/动画素材/'):
  stage='地图动画叠加素材'; state='新增素材；规格与透明度已核，尚未在实际动画合成中验收'; basis='动画素材批次任务单、README登记与制作检查记录'; advice='仅作为独立叠加元素使用；进入成片前检查实际运动、色彩与边缘'
  asset_uses={
   'slash_ink_1.png':'黑墨单道斜劈笔触，供诛杀动作按笔锋擦出','slash_ink_2.png':'黑墨弧形横扫笔触，供诛杀动作按笔锋擦出','slash_ink_3.png':'黑墨交叉短笔触，供处斩/诛杀动作叠加',
   'slash_red_1.png':'暗朱砂单道斜劈笔触，供诛杀动作按笔锋擦出','slash_red_2.png':'暗朱砂弧形横扫笔触，供诛杀动作按笔锋擦出','slash_red_3.png':'暗朱砂交叉短笔触，供处斩/诛杀动作叠加',
   'splash_1.png':'暗朱砂全向飞溅，供刀痕后缩放淡入','splash_2.png':'向右甩出的暗朱砂飞溅，供刀痕后缩放淡入','splash_3.png':'稀疏大滴暗朱砂飞溅，供轻量效果叠加','splash_4.png':'密集细点暗朱砂喷溅，供飞溅层次叠加','splash_5.png':'黑墨全向飞溅，供非流血场合的刀痕后叠加',
   'scroll_blank.png':'空白黄色绫面诏书卷轴，供左右展开后程序排字','frame_auspicious.png':'泥金祥云椭圆环框，供登基镜头围绕人物缓慢旋转',
  }
  # New batches keep their asset purposes in the existing README registry.
  for line in (ROOT/'03_素材/动画素材/README.md').read_text(encoding='utf-8-sig').splitlines():
   if not line.startswith('|'): continue
   cells=[cell.strip().strip('`') for cell in line.strip('|').split('|')]
   if len(cells)>=3 and cells[0].endswith('.png'): asset_uses.setdefault(cells[0],cells[2])
  if name in asset_uses: use=f'动画素材「{name}」：{asset_uses[name]}；由Codex内置ImageGen生成'
  elif '/对照/' in rel:
   state='素材对照/检查记录；不代表实际动画合成已验收'
   if '制作检查' in name: use='动画素材批次生成来源、提示词、重做记录、最终SHA-256和像素检查结果'
   elif '2x2' in name: use='动画素材贴图2×2拼接预览，检查连续重复后的边缘与纹理'
   else: use='动画素材批次浅灰/深灰双底对照图，用于检查透明边缘与构图'
  elif name=='README.md': use='动画素材目录说明：登记各批次文件、尺寸、用途、日期及生成工具'; state='素材登记与使用说明'
  elif name.startswith('codex-任务-'): use=f'{stem}：制作任务与验收规格；约束资产内容、路径和像素检查'; state='批次任务说明'
  # Batch 6 contains opaque dialogue backgrounds, unlike cutout props.
  if rel.startswith('03_素材/动画素材/第6批/'):
   stage='人物对话场景底图'; state='1920×1080 RGB不透明；已检查留空区、无人无字；待具体剧集合成预览'
   advice='作为立绘后方背景使用；中央下方留空，四边深褐柔暗角用于地图叠化'
  elif '/对照/' in rel and name.startswith('第6批-'):
   if '留空自查' in name: use='第6批九张场景底图留空自查：框出中央60%宽×下方40%高区域'
   elif '对照' in name: use='第6批九张场景底图对照：每张叠两个大灰色人形示意立绘位置'
  if name.endswith('-v1.png'):
   state='返工前旧版留档；已由同目录原文件名的新图替代'
   advice='仅供返工对照与追溯；动画使用同目录不带-v1的现行素材'
 m=re.search(r'world[_-](bc)?(\d+)',stem,re.I)
 if m: era=('前' if m[1] else '')+m[2]+'年（仅文件名标示，需核）'
 return use,stage,state,basis,group,era,advice

headers=['编号','功能分区','相对路径','文件名','格式','文件大小字节','具体用途','工作流阶段','使用状态','用途依据','依赖组','年代或题材','原路径','来源说明','新路径','迁移方式','原SHA256','当前SHA256','迁移校验','管理建议']
files={p.relative_to(ROOT).as_posix():p for p in walk(ROOT)}
for rel in DYNAMIC: files.setdefault(rel,ROOT/rel)
rows=[]; counts=Counter(); sizes=Counter(); duplicates=Counter(); unknown=0; missing=[]
for idx,(rel,p) in enumerate(sorted(files.items()),1):
 old=prior.get(str(p).lower(),{}); prev=old.get('previous',{})
 use,stage,state,basis,group,era,advice=purpose(p,rel,prev)
 dynamic=rel in DYNAMIC; size=None if dynamic else p.stat().st_size; current='' if dynamic else digest(p)
 source=old.get('source',''); original=old.get('sha256_before',''); mode='移动' if old else '本区新增'
 check='移动时SHA-256一致；迁移后路径适配' if str(p).lower() in adapted else '移动时及当前SHA-256一致'
 if old and current and current!=original and str(p).lower() not in adapted: check='移动时一致；随后内容有变化，待核实'
 if not old:
  check='本区新增，无移动对比'
  if '/GEOlayers瓦片依赖/' in rel:
   source=tiles.get(p.name,''); mode='复制外部AE依赖'; original=digest(Path(source)) if source and Path(source).exists() else ''; check='复制SHA-256一致' if original==current and original else '复制来源待核'
 if dynamic: check='动态清单，不做自身字节数与哈希'
 section=rel.split('/')[0] if '/' in rel else '根目录导航'
 counts[section]+=1; sizes[section]+=size or 0
 if '推定' in basis: unknown+=1
 upstream=prev.get('来源路径','') or old.get('reason','') or ('AE实际引用的外部缓存' if mode=='复制外部AE依赖' else '本次迁移管理新增')
 rows.append([f'HS-{idx:05}',section,rel,p.name,p.suffix.lower(),size,use,stage,state,basis,group,era,source,upstream,str(p),mode,original,current,check,advice])
 if current: duplicates[current]+=1
for r in proof['records']:
 if not Path(r['destination']).is_file(): missing.append(r['destination'])
summary={'physical_files':len(rows),'moved_original_files':proof['files'],'moved_original_bytes':proof['bytes'],'copied_ae_tiles':len(tiles),'physical_bytes_excluding_dynamic_indexes':sum(sizes.values()),'counts_by_section':dict(counts),'bytes_by_section':dict(sizes),'inferred_purposes':unknown,'moved_missing':missing,'missing_optional_evidence':[] if ae_before_path.is_file() else [str(ae_before_path)],'identical_content_groups':sum(v>1 for v in duplicates.values()),'dynamic_indexes':sorted(DYNAMIC),'junctions_and_node_modules':'excluded; no duplicate physical storage counted'}
(CTL/'inventory-data.json').write_text(json.dumps({'headers':headers,'rows':rows},ensure_ascii=False),encoding='utf-8')
(CTL/'inventory-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
md=['# 逐文件用途说明','',f'目录：`D:\\history\\codx_3 history studio`。更新：{date.today().isoformat()}。','','本表覆盖 **'+str(len(rows))+' 个物理文件**；Windows Junction与运行时node_modules不重复计数。每行提供用途、阶段和状态；原路径、来源依据、依赖组及校验详见[CSV](文件用途清单.csv)。','','2327个原文件移动时SHA-256全部一致；'+str(ADAPT_COUNT)+'项当前文件/工程后来为新路径适配。四份动态索引列入清单，但不填自身字节数和哈希，避免无限递归。用途可能来自既有审阅、格式结构或文件名推定，CSV有逐项依据。','','## 分区汇总','','| 分区 | 文件数 | 体积 GiB（不含动态索引） |','|---|---:|---:|']
for sec,n in counts.items(): md.append(f'| {sec} | {n} | {sizes[sec]/1024**3:.3f} |')
md+=['','这些是功能分区，不是每个文件都已审定为可公开使用或史实准确。原数据包、SHP配套和工程资产保持成组。相同哈希并不自动意味着可以单独删除依赖文件。','']
last=None
def esc(s): return str(s).replace('|','\\|').replace('\n',' ').replace('\r',' ')
for r in rows:
 if r[1]!=last:
  last=r[1]; md+=['',f'## {last}','','| 文件 | 具体用途 | 阶段 / 状态 |','|---|---|---|']
 target=r[2].replace('>','%3E').replace('<','%3C')
 md.append(f'| [{esc(r[2])}](<{target}>) | {esc(r[6])} | {esc(r[7])} / {esc(r[8])} |')
(ROOT/'文件用途说明.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
if missing: raise SystemExit('Missing moved files')
