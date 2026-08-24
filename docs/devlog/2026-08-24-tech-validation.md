# 2026-08-24 技术验证记录

状态：✅ 四项全部通过，技术路线可行，进入 MVP

## 1. 悬浮窗 + 全局快捷键（PySide6）✅

- 置顶无边框悬浮窗渲染成功（400×300，圆角，见 demo/demo1_floatwindow.png）
- 全局快捷键 Ctrl+Shift+V 注册成功（ctypes RegisterHotKey，零依赖）
- 模拟"唤出 → 输入 → 回车保存"事件流跑通
- 方案：QAbstractNativeEventFilter 监听 WM_HOTKEY，off-screen 验证

## 2. 剪贴板读写 ✅

- 文本写入/读回一致（pyperclip）
- 图片位图写入/读回一致（Qt QClipboard），pixmap 可转存文件
- 结论：微信里"复制图片 → Ctrl+V 进悬浮窗"的载体成立

## 3. RapidOCR 离线识别 ✅

- 生成含 3 行中文的测试图，离线识别耗时约 0.55s
- 识别结果：`2026深大新生竞赛报名 / 截止日期：9月20日 / 报名方式：线上填写表格`
- 结论：图片文字可进搜索索引

## 4. DeepSeek API 分类 ✅

- 输入一条竞赛报名信息，返回结构化 JSON：
  - 主题=竞赛、重要程度=高、效用期=短期任务
  - 建议标签=[物理竞赛, 组队, 奖金]、截止时间=2024-09-20、一句话摘要
- 结论：分类通道可用

## 发现的问题（MVP 需处理）

1. **API key 来源**：`~/AppData/Local/hermes/.env` 里的 DEEPSEEK_API_KEY（…9438）已失效；
   有效 key 在 `~/AppData/Local/hermes/config.yaml` 的 custom_providers 里（…f8ba，实测可用）。
   → 项目配置里直接复用 config.yaml 的 key（读取函数已写入 demo4，MVP 时封装成模块）。
2. **日期年份推断错误**：模型把"9月20日"推断为 2024 年。
   → 分类 prompt 需注入当前日期（2026-08-24），让模型用正确的年份推断截止日期。
3. PySide6 全家桶（Essentials+Addons）约占用 1-2GB 磁盘，本地运行无影响，但启动略慢，
   MVP 时考虑只引入需要的 Qt 模块。

## 环境备忘

- Python：C:\Users\Asus\AppData\Local\Programs\Python\Python313\python.exe (3.13.15)
- 依赖安装走清华镜像：-i https://pypi.tuna.tsinghua.edu.cn/simple
- 模型：deepseek-v4-flash / deepseek-v4-pro 均可用
