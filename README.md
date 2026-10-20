# 文件夹整理工具

Windows 桌面文件整理工具，使用 Python + Tkinter + CustomTkinter 编写，界面为苹果风浅色配色。

扫描工作目录后，可以按条件批量重命名、按规则分类到子文件夹、查找重复或相似文件。所有改动都先生成预览，确认后才会执行，并写入可撤销的操作日志。

详细用法：[docs/usage.md](docs/usage.md) · 常见问题：[docs/faq.md](docs/faq.md) · 更新记录：[CHANGELOG.md](CHANGELOG.md)

## 功能

- **扫描**：选择工作目录，可包含子文件夹与隐藏文件；默认跳过 Windows 隐藏属性，`.file_organizer_logs/` 始终不参与扫描。右侧预览表显示状态、原文件、大小、类型、修改时间、所在文件夹和目标位置。
- **预览表**：点击列名按该字段升序 / 降序排序；右上角「显示字段」可勾选要显示的列，字段与排序会记住，下次启动继续使用。
- **批量重命名**：按文件名（支持正则）、类型、大小、修改时间筛选；支持前缀、后缀、连续编号、查找替换、中文大小写选项和修改扩展名。
- **分类整理**：按文件类型、扩展名、名称关键词、修改年月、大小或正则提取结果，把文件移动到对应的子文件夹。
- **查找重复**：文件名相似、大小接近、字节相同三种条件可叠加使用（同时满足）；哈希阶段多线程读盘。结果按组展示，多余的副本移动到 `重复文件/`，不删除、可撤销。
- **历史与撤销**：每次执行都会在 `.file_organizer_logs/` 写入 JSONL 日志，可撤销上一次操作或选择指定日志；撤销会校验路径范围。
- **正则帮助**：右上角「正则帮助」按钮打开教学窗口，包含基础语法和常用模板，模板可一键复制。

## 使用

### 运行

源码方式（需要 Python 3.10+）：

```powershell
python -m pip install -r requirements.txt
python run.py
```

打包版：双击 `FileOrganizer.exe`（整个文件夹需保持完整）。

### 基本流程

1. 点击「浏览…」选择工作目录，按需勾选「包含子文件夹」「包含隐藏文件」，然后「扫描文件」。
2. 在左侧四个页签中设置规则：批量重命名 / 分类整理 / 查找重复 / 历史与撤销。
3. 点击对应页签的搜索或预览按钮，在右侧表格检查原文件、目标位置、类型、大小和修改时间；点击列名可排序，右上角「显示字段」可增减列。
4. 确认无误后点击「执行预览操作」；如果结果不符合预期，到「历史与撤销」恢复。

建议先用少量测试文件熟悉规则。程序不会覆盖同名文件，遇到重名会自动追加 `(1)`、`(2)`；执行后点击「扫描文件」刷新列表。

### 命令行查重

```powershell
python -m file_organizer.cli D:\videos
python -m file_organizer.cli D:\videos --ext .mp4 .mkv --hash --json result.json
```

完整参数、JSON 输出格式与示例见 [docs/usage.md](docs/usage.md)。

## 架构

```text
run.py / python -m file_organizer     程序入口
file_organizer/
├─ app.py          主窗口：目录扫描、预览表格、后台任务、撤销入口
├─ tabs.py         四个页签的表单与预览流程
├─ preview.py      预览表字段、Action 行构建、类型 / 修改时间格式化、排序
├─ preferences.py  显示字段与排序设置的原子持久化
├─ core.py         扫描/筛选、FileEntry、重命名与分类规则、执行、日志与撤销
├─ duplicates.py   相似文件名、大小分组、哈希确认、叠加查重与多线程读盘
├─ cli.py          命令行查重
├─ widgets.py      统一风格控件：卡片、按钮、输入框、多选下拉、分段页签
├─ theme.py        配色、字体、ttk 样式
├─ regex_help.py   正则基础教学与常用模板窗口
├─ utils.py        扩展名/文件大小格式化、资源路径、依赖缺失提示
└─ assets/         窗口与程序图标
tests/             核心、查重、预览、偏好与界面防断裂测试
docs/              详细用法与常见问题
```

数据流：

```text
扫描目录 → 筛选/规则计算 → 生成 Action 预览 → 表格确认 → 执行并写日志 → 按日志撤销
```

界面层只负责收集参数和展示结果；重命名、分类、查重的判定都集中在 `core.py` 与 `duplicates.py`，便于单元测试。执行前所有操作以 `Action` 列表存在，只有用户确认后 `OrganizerEngine.execute()` 才会真正移动或重命名文件。

### 测试

```powershell
python -m unittest discover -v
python -m mypy file_organizer/core.py file_organizer/duplicates.py file_organizer/preview.py file_organizer/utils.py file_organizer/preferences.py file_organizer/cli.py
```

覆盖扫描、筛选、重命名、分类、正则提取、执行、撤销、查重与清理往返、预览字段排序、设置持久化以及 CTk 私有 API 降级。CI 还会对核心模块运行 `mypy` 类型检查。

### 打包

```powershell
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean FileOrganizer.spec
```

采用 onedir（文件夹）模式且不启用控制台窗口，产物在 `dist/FileOrganizer/`，本身体积比单文件版小、启动也更快。

### 已知限制

程序目前没有统一添加 `\\?\` 长路径前缀，仍受 Windows 传统 260 字符路径限制；文件名组件会截断到 255 字符以内，深层目录仍可能操作失败，失败条目不会覆盖已有文件。详见 [docs/faq.md](docs/faq.md)。
