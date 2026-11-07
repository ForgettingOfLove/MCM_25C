# Q1 数据工程（采集 + 预处理）

2025 年第十届数维杯 C 题第一问的**数据环节**：先采集，再清洗。

从 NOAA NCEI 全球逐日气象数据集（GSOD）抓取 **7 城 × 20 年 × 清明假期 3 天** 的日降水量，
产出结构化长表、缺失报告、站点映射与汇总 JSON；再由预处理把缺失填上、把长表摊成
宽表与建模序列，供后续「雨纷纷」判定与 ARIMA 建模使用。

| 项目 | 取值 |
|---|---|
| 城市 | 西安、吐鲁番、婺源、杭州、毕节、武汉、洛阳 |
| 年份 | 2006—2025（20 年） |
| 日期 | 每年 4/4、4/5、4/6（清明假期） |
| 数据源 | `ncei.noaa.gov` GSOD `access/{年}/{站号}.csv`，缺失回退 `archive/{年}.tar.gz` |
| 记录规模 | 7 × 20 × 3 = **420 条日记录**，清洗后仍 420 条（缺失已填补） |
| 两阶段边界 | `main.py` 只取数不改数；`preprocess.py` 才动数，且改动逐条记录 |

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

# 4. 清洗（读上一步的 output/tables/rain_2006_2025.csv）
python preprocess.py
```

Windows cmd 手动版（不想用脚本时）：

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
python preprocess.py
```

> 依赖仅三个，两阶段共用：`requests`（下载）、`pandas`（解析、填补与落表）、`tqdm`（进度条）。
> Python 要求 **3.10+**（代码用了 `X | None` 类型标注）。

---

## 二、目录结构

```
项目文件/
├── main.py                     # 采集入口：命令行参数 + 日志 + 汇总打印
├── preprocess.py               # 预处理入口：命令行参数 + 日志 + 汇总打印
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
├── q1clean/                    # 预处理包（同样一个文件一件事）
│   ├── __init__.py
│   ├── config.py               # CleanSettings  判据阈值、缺失口径、产物命名
│   ├── loader.py               # CollectTableLoader  读采集表、校验网格、补缺行
│   ├── imputer.py              # ClimatologyImputer  历年同期均值填补
│   ├── features.py             # 纯函数        判据、量级、宽表、序列
│   ├── quality.py              # QualityChecker 逐城逐年体检
│   ├── pipeline.py             # Preprocessor  串起全流程
│   └── reporter.py             # CleanReporter 三张数据表 + 两张报告 + JSON
├── data/
│   ├── raw/                    # 原始 CSV 缓存，一站一年一个文件（git 忽略）
│   └── processed/              # 清洗产物：rain_all / rain_wide / series_rain
└── output/
    ├── tables/                 # 结果表与报告
    └── logs/                   # fetch_log.txt、clean_log.txt
```

### 文件 / 类 对照 · 采集

| 文件 | 类 / 函数 | 职责 |
|---|---|---|
| `paths.py` | `ProjectPaths` | 全部目录与文件路径；`ensure()` 建目录，`raw_file()` 给缓存路径 |
| `config.py` | `Station`、`RequestSettings` | 站点映射（站号/坐标/替代说明）、年份、清明三天、请求超时重试 |
| `http_client.py` | `GsodClient` | `fetch()` 取回原始字节；404 自动回退 archive 流式抽取 |
| `parser.py` | `parse_prcp()`、`load_station_year()`、`profile_year()`、`extract_window()` | 不做 IO 之外的副作用，纯解析 |
| `collector.py` | `RainCollector`、`CollectResult` | 跑循环，产出日记录 + 年度报告 |
| `reporter.py` | `ResultReporter` | 固化列序、写 CSV/JSON、生成汇总 |

### 文件 / 类 对照 · 预处理

| 文件 | 类 / 函数 | 职责 |
|---|---|---|
| `q1clean/config.py` | `CleanSettings` | 判据阈值（0.1–9.9 mm、≥3 h）、缺失状态、填补最小样本、产物命名 |
| `q1clean/loader.py` | `CollectTableLoader` | `resolve()` 找输入表，`load()` 校验列、去重、按网格补行 |
| `q1clean/imputer.py` | `ClimatologyImputer` | 同城同月日、其余年份可靠观测均值；记录每一条填补的依据与样本数 |
| `q1clean/features.py` | `rain_level()`、`is_small_rain()`、`judge_yufengfen()`、`add_flags()`、`to_wide()`、`to_series()` | 纯函数，不落盘；判据缺时长时返回 `None`，不当 `False` |
| `q1clean/quality.py` | `QualityChecker` | 逐城（零方差/填补率/替代站）+ 逐年（补了几天/三日全填补） |
| `q1clean/pipeline.py` | `Preprocessor`、`CleanResult` | 读 → 填 → 派生 → 体检，一条链跑完 |
| `q1clean/reporter.py` | `CleanReporter` | 数据表进 `data/processed/`，报告进 `output/tables/` |

### 逻辑结构图 · 采集

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

### 逻辑结构图 · 预处理

```
                    preprocess.py (argparse + logging)
                              │
                              ▼
                       ProjectPaths.ensure()
                              │
                              ▼
                CollectTableLoader.load()          ← 读 output/tables/rain_*.csv
                              │                      校验列 / 去重 / 补齐 420 行网格
                              ▼
                  ClimatologyImputer.fill()        ← 只填「没有数」的格子
                              │                      同城同月日其余年份均值（n≥5）
                              │                      三级回退：同期 → 同期含trace → 三日全期
                              ▼
                    features.add_flags()           ← quality / prcp_level /
                              │                      prcp_in_small_range / dur_h / is_yufengfen
                    ┌─────────┴─────────┐
                    ▼                   ▼
               to_wide()            to_series()
           (城×年，三日展开)      (建模序列，一城一年)
                    │                   │
                    └─────────┬─────────┘
                              ▼
                    QualityChecker.check()         ← 全零序列 / 填补率 / 三日全填补
                              │
                              ▼
                    CleanReporter.write_all()
                              │
      ┌───────────────┬───────┴────────┬──────────────┬──────────────┐
      ▼               ▼                ▼              ▼              ▼
 data/processed/  data/processed/  data/processed/  output/tables/  output/tables/
 rain_all.csv     rain_wide.csv    series_rain.csv  clean_report    clean_summary
   (420 行)         (140 行)          (140 行)         .csv(7 行)      .json
```

---

## 三、命令行用法

### 采集

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

### 预处理

```bash
python preprocess.py                              # 全量：自动找 output/tables/rain_2006_2025.csv
python preprocess.py --input output/tables/rain_2020_2025.csv   # 指定输入表
python preprocess.py --city 西安 武汉              # 只清洗指定城市
python preprocess.py --years 2015 2025            # 只清洗指定年份
python preprocess.py --min-sample 8               # 同期均值至少 8 年（默认 5）
python preprocess.py --strict                     # 有填不上的缺失就中断，退出码 3
```

> 预处理产物文件名固定（`rain_all.csv` 等），**子集运行会覆盖全量结果**。
> `--city` / `--years` 只用于调试，交付前务必跑一次不带参数的全量。

---

## 四、输出说明

### 采集

#### 1. `output/tables/rain_2006_2025.csv` —— 主表（420 行）

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

#### 2. `output/tables/fetch_report.csv` —— 年度报告（140 行）

一城一年一行：`days_ok` / `days_missing` / `status`（完整·部分缺失·全缺）、
全年行数 `year_rows`、全年降水日数 `year_rainy_days`、属性 I 天数 `year_I_days`、
`station_suspect`（全年 0 天降水>0 → 判该站降水字段不可用）、`reason` 汇总原因。

#### 3. `output/tables/stations.csv` —— 站点映射

城市 ↔ 站号 ↔ 站点坐标 ↔ 城市坐标 ↔ 替代理由。论文附录与 `docs/站点映射表.md` 直接用这张表。

#### 4. `output/tables/fetch_summary.json` —— 汇总

给后续脚本读的机读版：来源统计、状态计数、逐城完整年份 / 部分缺失年份 / 全缺年份。

#### 5. `output/logs/fetch_log.txt` —— 运行日志

逐站逐年一行，含来源与缺失原因，排查问题先看它。

### 预处理

#### 1. `data/processed/rain_all.csv` —— 清洗后长表（420 行）

一城一年一天一行，是论文数据字典对应的那张表。

| 列 | 含义 |
|---|---|
| `city` / `station_id` / `station_name` / `station_role` | 同采集表，站点身份 |
| `year` / `date` / `month_day` | 年 / 日期（YYYY-MM-DD）/ 月日（04-04） |
| `prcp_inch` | 原始英寸值，仅供复核 |
| `prcp_raw_mm` | 采集阶段换算出的毫米值，**填补前**，缺失为空 |
| `prcp_mm` | **建模用值**：填补后的毫米值，全表无空 |
| `prcp_level` | GB/T 28592 等级：无雨 / 小雨 / 中雨 / 大雨 / 暴雨 / 大暴雨 / 特大暴雨 |
| `prcp_status` | 采集阶段状态，保留原样（`ok`/`dry_I`/`trace`/`missing`/`no_row`…） |
| `prcp_attr` | GSOD 的 `PRCP_ATTRIBUTES` 原字母 |
| `quality` | **最终值来源**：`ok` / `dry_I` / `trace` / `imputed` |
| `prcp_in_small_range` | 是否落在小雨量级（0.1–9.9 mm），`是` / 空 |
| `is_filled` | 是否由填补得来，`是` / 空 |
| `impute_basis` | 填补依据，如 `同期均值 n=18`（月日 + 参与年数） |
| `dur_h` | 降雨时长（h）——**本阶段为空**，等 rp5.ru / ISD 接入 |
| `is_yufengfen` | 「雨纷纷」判定——**本阶段为空**，缺时长维度 |
| `source` | `access` / `archive` / `cache`，数据来源 |
| `note` | 问题说明；填补行写明依据与原状态 |

#### 2. `data/processed/rain_wide.csv` —— 三日宽表（140 行）

一城一年一行，`prcp_0404` / `prcp_0405` / `prcp_0406` 三日展开，另加：

| 列 | 含义 |
|---|---|
| `prcp_sum_mm` | 假期三日累计降水（mm），**主序列** |
| `prcp_max_mm` | 三日最大单日降水 |
| `rainy_days` | 三日中降水 > 0 的天数 |
| `small_rain_days` | 三日中落在小雨量级的天数 |
| `filled_days` | 三日中由填补得来的天数 |
| `all_imputed` | 三日全为填补值，`是` / 空 —— **该年不是真实观测** |

#### 3. `data/processed/series_rain.csv` —— 建模序列（140 行）

宽表去掉三个日值列后的版本，一城一年一行，`04_arima.py` 直接 `groupby("city")` 取 20 点序列。

#### 4. `output/tables/clean_report.csv` —— 逐城体检（7 行）

`days_obs`（原始有数）/ `days_filled` / `fill_rate` / `days_trace` / `days_dry_I` /
`prcp_mean_mm` / `prcp_max_mm` / `zero_ratio` / `series_zero_years` / `series_std` /
`usable_for_arima` / `issue`。当前结论：吐鲁番 `usable_for_arima` 为空（全零序列），其余 6 城可用。

#### 5. `output/tables/clean_by_year.csv` —— 逐年明细（140 行）

带三日值与 `filled_days` / `all_imputed` / `raw_missing_days`，哪一年补了几天一眼看到。
当前有两年三日全靠填补：**西安 2006**、**婺源 2024**。

#### 6. `output/tables/clean_summary.json` —— 清洗汇总

机读版：口径（判据阈值、时长是否可用）、填补明细（18 条逐条记录依据与样本数）、
网格校验（期望 420 / 实到 420 / 补行 0 / 重复 0）、统计与逐城结论。

#### 7. `output/logs/clean_log.txt` —— 运行日志

读表、填补、体检逐条记录，重跑对不上数时先看它。

---

## 五、口径与坑（动手前先看）

1. **单位**。GSOD 的 `PRCP` 是**英寸**，`prcp_mm` 已 ×25.4。写论文时只用 mm 列。
2. **缺测哨兵 99.99**。99.99 英寸不是雨，是缺测，已在解析处拦掉，不会混进序列。
3. **属性 H / I 不能等同正常 0**。属性 I 表示当天根本没有降水报告，数值 0.00 只是占位；
   属性 H 表示报 0 但观测到了降水现象。两者都按 0 记，但 `prcp_status` 单独标出，
   敏感性分析时可以剔除。
4. **西安 2006 年**。泾河站 2006-10 才建站，该年三日全是 `no_row`，已由预处理按
   同期均值填补（n=18/19），但**这一年三日全是填补值**，不是真实观测，建模时要标出来
   （看 `all_imputed` 列）。同样情况还有婺源 2024（景德镇当年 4/4–4/6 整段无记录）。
5. **婺源、洛阳是替代站**。婺源用景德镇（约 64 km），洛阳用孟津（约 22 km）。
   写结论时必须交代，否则等于把邻站的雨说成本市的雨。
6. **限速**。公共服务器，默认 0.6 s 间隔 + 3 次指数退避重试。`data/raw` 有缓存，
   重跑不会重复下载；`--raw-dir` 可直接复用别人的 `raw/`。
7. **文件名随年份变**。`--years 2020 2025` 产出 `rain_2020_2025.csv`，全量才是
   `rain_2006_2025.csv`。下游脚本要么读 `fetch_summary.json`，要么固定用全量名。
8. **填补口径**：同城、同月日、其余年份的**可靠观测**均值，三级回退——同期（排除 trace）
   → 同期（含 trace）→ 该城三日全期。当前 18 条全部走第一级，样本 18–19 年。
   只填 `no_row` / `missing` / `no_report` / `no_file` 这四种「没有数」的状态，
   `dry_I` / `trace` 是「有数但带标记」，值不动，标记留在 `quality` 列。
9. **吐鲁番是零方差序列**。20 年清明三日全为 0（全年确实有降水，只是 4 月初没有），
   ARIMA 对它无信息可提取。`clean_report.csv` 里 `usable_for_arima` 留空，
   建模阶段要么单独说明，要么按气候态频率给 0 概率——不要硬拟合出个假模型。
10. **降雨时长拿不到**。GSOD 没有时长字段，`dur_h` 与 `is_yufengfen` 整列为空，
    `--strict` 也不会因此报错。判据函数 `judge_yufengfen()` 在缺时长时返回 `None`（未知），
    不当 `False`：现在能给的只有降水维度（`prcp_in_small_range`）。
    时长数据接入后重跑 `preprocess.py` 即可，口径不用改。
11. **序列口径是一城一年一个观测（n=20）**。`prcp_sum_mm` = 假期三日累计，
    不做「三日拼成 60 点」——原文 5.2.2 的 60 点口径与 5.3 的 20 点预测口径不一致，
    复现统一取 20 点，理由写进论文。

---

## 六、本阶段不做的事

| 不做 | 交给谁 |
|---|---|
| 降雨时长序列、`dur_h` 填值 | 独立数据源（rp5.ru / NOAA ISD），`02b_duration.py` |
| `is_yufengfen` 布尔列落地（缺时长） | 时长接入后重跑 `preprocess.py` |
| 敏感性分析（trace 剔除 / 2h·3h·6h 三档） | 建模阶段按 `quality` 列分组重算 |
| ADF / LB / ACF/PACF / ARIMA（含吐鲁番的降级处理） | `04_arima.py` |
| 7:3 划分、2025 留出、基线对比 | `05_validate.py` |

`data/processed/` 已有三张表；下一步直接读 `series_rain.csv` 建模。

---

## 七、与其他目录的关系

| 目录 | 说明 |
|---|---|
| `../code/` | 第一版采集脚本（单文件、标准库 urllib）。本工程是它的工程化重写：改用 `requests` + `pandas`，路径统一走 `pathlib`，拆成单职责模块，产出表结构保持一致，可直接互换 |
| `../论文复现分工方案.md` | 分工与时间线。本工程对应 **C1（站点匹配 + 批量下载）** 与 **C2（清洗与长表）**；C3 时长、C4 图、C5 建模不在本工程内 |
| `../../document/` | 赛题与待复现论文 PDF |
