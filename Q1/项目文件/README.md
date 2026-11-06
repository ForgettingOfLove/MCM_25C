# Q1 数据采集工程

2025 年第十届数维杯 C 题第一问的**数据采集环节**（只采集，不做预处理）。

从 NOAA NCEI 全球逐日气象数据集（GSOD）抓取 **7 城 × 20 年 × 清明假期 3 天** 的日降水量，
产出结构化长表、缺失报告、站点映射与汇总 JSON，供后续缺失填补、序列构造与 ARIMA 建模使用。

| 项目 | 取值 |
|---|---|
| 城市 | 西安、吐鲁番、婺源、杭州、毕节、武汉、洛阳 |
| 年份 | 2006—2025（20 年） |
| 日期 | 每年 4/4、4/5、4/6（清明假期） |
| 数据源 | `ncei.noaa.gov` GSOD `access/{年}/{站号}.csv`，缺失回退 `archive/{年}.tar.gz` |
| 记录规模 | 7 × 20 × 3 = **420 条日记录** |
| 范围 | 采集 + 落表。**不做**单位统一后的填补、不做序列构造、不做建模 |

---

## 一、快速开始

```bash
# 1. 建虚拟环境 + 装依赖（Git Bash / macOS / Linux）
bash scripts/setup_env.sh

# 2. 激活
source .venv/Scripts/activate      # Windows (Git Bash)
# .venv\Scripts\activate           # cmd
# source .venv/bin/activate        # macOS / Linux

# 3. 抓数据
python main.py
```

Windows cmd 手动版（不想用脚本时）：

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

> 依赖仅三个：`requests`（下载）、`pandas`（解析与落表）、`tqdm`（进度条）。
> Python 要求 **3.10+**（代码用了 `X | None` 类型标注）。

---

## 二、目录结构

```
项目文件/
├── main.py                     # 入口：命令行参数 + 日志 + 汇总打印
├── requirements.txt            # 依赖清单
├── .gitignore
├── README.md
├── scripts/
│   └── setup_env.sh            # 一键建 .venv 并装依赖
├── q1collect/                  # 采集包（一个文件一件事）
│   ├── __init__.py
│   ├── paths.py                # ProjectPaths  目录与路径（pathlib）
│   ├── config.py               # Station / RequestSettings  年份、站点、请求参数
│   ├── http_client.py          # GsodClient    requests 下载、重试、缓存、archive 回退
│   ├── parser.py               # 纯函数        GSOD 解析、PRCP 语义、三日提取
│   ├── collector.py            # RainCollector 城市×年份编排
│   └── reporter.py             # ResultReporter 三张表 + JSON 落盘
├── data/
│   ├── raw/                    # 原始 CSV 缓存，一站一年一个文件（git 忽略）
│   └── processed/              # 预处理产物（本阶段留空）
└── output/
    ├── tables/                 # 结果表
    └── logs/                   # fetch_log.txt
```

### 文件 / 类 对照

| 文件 | 类 / 函数 | 职责 |
|---|---|---|
| `paths.py` | `ProjectPaths` | 全部目录与文件路径；`ensure()` 建目录，`raw_file()` 给缓存路径 |
| `config.py` | `Station`、`RequestSettings` | 站点映射（站号/坐标/替代说明）、年份、清明三天、请求超时重试 |
| `http_client.py` | `GsodClient` | `fetch()` 取回原始字节；404 自动回退 archive 流式抽取 |
| `parser.py` | `parse_prcp()`、`load_station_year()`、`profile_year()`、`extract_window()` | 不做 IO 之外的副作用，纯解析 |
| `collector.py` | `RainCollector`、`CollectResult` | 跑循环，产出日记录 + 年度报告 |
| `reporter.py` | `ResultReporter` | 固化列序、写 CSV/JSON、生成汇总 |

### 逻辑结构图

```
                    main.py (argparse + logging)
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
        ProjectPaths     RequestSettings    STATIONS
        (paths.py)        (config.py)      (config.py)
              │               │                │
              └───────────────┴────────────────┘
                              ▼
                        RainCollector            ← 城市 × 年份 双循环
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              GsodClient.fetch()    extract_window() / profile_year()
              (http_client.py)        (parser.py)
                    │                   │
        ┌───────────┴──────────┐        │
        ▼                      ▼        │
  access/{年}/{站}.csv    archive/{年}.tar.gz
        │            (404 时流式抽取)
        └───────────┬──────────┘
                    ▼
             data/raw/{站号}_{年}.csv      ← 缓存，二次运行直读
                    │
                    ▼
              parse_prcp() → (mm, 状态)
                    │
                    ▼
            CollectResult(records, report)
                    │
                    ▼
             ResultReporter.write_all()
                    │
      ┌─────────────┼──────────────┬──────────────┐
      ▼             ▼              ▼              ▼
rain_2006_2025  fetch_report   stations.csv  fetch_summary.json
   .csv(420行)    .csv(140行)
```

---

## 三、命令行用法

```bash
python main.py                          # 全量：7 城 × 2006—2025
python main.py --city 杭州 洛阳          # 只抓指定城市
python main.py --years 2020 2025        # 只抓指定年份（文件名随年份变）
python main.py --source archive         # 强制走 /archive/*.tar.gz
python main.py --source access          # 只走分站切片，404 不救
python main.py --no-cache               # 忽略 data/raw 重新下载
python main.py --raw-dir ../code/raw    # 复用现有缓存，一个请求都不发
python main.py --pause 0.3              # 改请求间隔（默认 0.6 s）
python main.py --list-cities            # 打印站点映射
python main.py --no-progress            # 关进度条（写进日志时更干净）
```

---

## 四、输出说明

### 1. `output/tables/rain_2006_2025.csv` —— 主表（420 行）

| 列 | 含义 |
|---|---|
| `city` | 城市名 |
| `station_id` | GSOD 站号（USAF+WBAN 共 11 位） |
| `station_name` | 站点英文名 + 中文注 |
| `station_role` | `本市站点` / `邻近替代站` |
| `year` / `date` | 年份 / 日期（YYYY-MM-DD） |
| `prcp_inch` | 原始值（英寸），保留以便复核 |
| `prcp_mm` | **换算后毫米值**（×25.4，两位小数），缺失为空 |
| `prcp_status` | 见下表，**下游清洗必看这一列** |
| `prcp_attr` | GSOD 的 `PRCP_ATTRIBUTES` 原始字母 |
| `source` | `access` / `archive` / `cache` |
| `note` | 该行的问题说明，正常行留空 |

`prcp_status` 取值（"可用"指可直接进序列）：

| 状态 | 含义 | 可用性 |
|---|---|---|
| `ok` | 属性 A–G，正常的日降水总量（G 最理想，24 h 报告） | ✅ 可用 |
| `dry_I` | 属性 I，当日无降水报告，按 0 记 | ⚠️ 可用但需标记 |
| `trace` | 属性 H，报 0 但观测有降水现象，按 0 记 | ⚠️ 数据不完整 |
| `no_report` | 属性 I 且无任何数值 | ❌ 不可当 0 |
| `missing` | PRCP 为缺测哨兵 99.99 或空 | ❌ 缺失 |
| `no_row` | 文件里没有这一天（如站点尚未建站） | ❌ 缺失 |
| `no_file` | 该站该年文件 404 | ❌ 缺失 |

### 2. `output/tables/fetch_report.csv` —— 年度报告（140 行）

一城一年一行：`days_ok` / `days_missing` / `status`（完整·部分缺失·全缺）、
全年行数 `year_rows`、全年降水日数 `year_rainy_days`、属性 I 天数 `year_I_days`、
`station_suspect`（全年 0 天降水>0 → 判该站降水字段不可用）、`reason` 汇总原因。

### 3. `output/tables/stations.csv` —— 站点映射

城市 ↔ 站号 ↔ 站点坐标 ↔ 城市坐标 ↔ 替代理由。论文附录与 `docs/站点映射表.md` 直接用这张表。

### 4. `output/tables/fetch_summary.json` —— 汇总

给后续脚本读的机读版：来源统计、状态计数、逐城完整年份 / 部分缺失年份 / 全缺年份。

### 5. `output/logs/fetch_log.txt` —— 运行日志

逐站逐年一行，含来源与缺失原因，排查问题先看它。

---

## 五、口径与坑（动手前先看）

1. **单位**。GSOD 的 `PRCP` 是**英寸**，`prcp_mm` 已 ×25.4。写论文时只用 mm 列。
2. **缺测哨兵 99.99**。99.99 英寸不是雨，是缺测，已在解析处拦掉，不会混进序列。
3. **属性 H / I 不能等同正常 0**。属性 I 表示当天根本没有降水报告，数值 0.00 只是占位；
   属性 H 表示报 0 但观测到了降水现象。两者都按 0 记，但 `prcp_status` 单独标出，
   敏感性分析时可以剔除。
4. **西安 2006 年**。泾河站 2006-10 才建站，该年三日全是 `no_row`（n=19），
   预处理阶段需填补或用邻站（凤翔 570250，约 144 km）补充。
5. **婺源、洛阳是替代站**。婺源用景德镇（约 64 km），洛阳用孟津（约 22 km）。
   写结论时必须交代，否则等于把邻站的雨说成本市的雨。
6. **限速**。公共服务器，默认 0.6 s 间隔 + 3 次指数退避重试。`data/raw` 有缓存，
   重跑不会重复下载；`--raw-dir` 可直接复用别人的 `raw/`。
7. **文件名随年份变**。`--years 2020 2025` 产出 `rain_2020_2025.csv`，全量才是
   `rain_2006_2025.csv`。下游脚本要么读 `fetch_summary.json`，要么固定用全量名。

---

## 六、本阶段不做的事

| 不做 | 交给谁 |
|---|---|
| 缺失值填补（历年同期均值 / 邻站回归） | 预处理 `02_clean.py` |
| 降雨时长序列（GSOD 无此字段） | 独立数据源，`02b_duration.py` |
| 「雨纷纷」判据落地、`is_yufengfen` 布尔列 | 建模手判据文档 + 预处理 |
| 长表转宽表、分城序列 | 预处理 |
| ADF / LB / ARIMA | `04_arima.py` |

`data/processed/` 已建好但为空，等预处理脚本产出。

---

## 七、与其他目录的关系

| 目录 | 说明 |
|---|---|
| `../code/` | 第一版采集脚本（单文件、标准库 urllib）。本工程是它的工程化重写：改用 `requests` + `pandas`，路径统一走 `pathlib`，拆成单职责模块，产出表结构保持一致，可直接互换 |
| `../论文复现分工方案.md` | 分工与时间线，本工程对应其 **C1（站点匹配 + 批量下载）** |
| `../../document/` | 赛题与待复现论文 PDF |
