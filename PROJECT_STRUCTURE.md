# 📁 项目结构说明

本文档详细说明了项目的文件组织结构和各部分的作用。

## 🏗️ 整体结构

```
freqtrade-render-ci/
├── 📚 文档和说明
│   ├── README.md                    # 项目主说明
│   ├── QUICKSTART.md               # 快速开始指南
│   ├── STRATEGY_README.md          # 策略详细说明
│   └── PROJECT_STRUCTURE.md        # 本文件
├── 🎯 核心策略文件
│   ├── scripts/local/final_optimized_strategy.py   # 独立策略实现（推荐）
│   └── user_data/strategies/EightPMHighLowStrategy.py  # Freqtrade策略
├── ⚙️ 配置文件
│   ├── config/
│   │   ├── eightpm_backtest.json   # 回测配置
│   │   └── base.json               # 基础配置
│   ├── requirements.txt            # Python依赖
│   └── Dockerfile                  # Docker配置
├── 🛠️ 脚本工具
│   ├── scripts/
│   │   ├── local/                  # 本地运行脚本
│   │   │   ├── test_strategy.py    # 独立策略测试
│   │   │   ├── run_local_backtest.sh  # 快速本地回测
│   │   │   ├── run_freqtrade_backtest.sh  # 完整回测
│   │   │   └── run_strategy.py     # 简化运行脚本
│   │   ├── ci/                     # CI/CD脚本
│   │   │   ├── prepare_backtest.sh # 环境准备
│   │   │   └── analyze_results.sh  # 结果分析
│   │   └── README.md               # 脚本使用说明
├── 🤖 自动化工作流
│   └── .github/workflows/
│       ├── backtest.yml            # 自动回测
│       └── manual-backtest.yml     # 手动回测
├── 📦 策略版本归档
│   ├── strategies_archive/
│   │   ├── simple_eightpm_strategy.py     # v2.0 简化版本
│   │   ├── optimized_eightpm_strategy.py  # v3.0 优化版本
│   │   ├── advanced_eightpm_strategy.py   # v4.0 进阶版本
│   │   ├── eightpm_strategy.py           # v1.0 基础版本
│   │   └── README.md                     # 版本说明
└── 🗂️ 数据和结果
    └── user_data/
        ├── strategies/             # Freqtrade策略目录
        ├── data/                  # 历史数据（.gitignore）
        ├── logs/                  # 日志文件（.gitignore）
        └── backtest_results/      # 回测结果（.gitignore）
```

## 🎯 核心文件说明

### 主要策略文件

| 文件 | 用途 | 特点 |
|------|------|------|
| `scripts/local/final_optimized_strategy.py` | 独立策略实现 | ✅ 无依赖，快速测试 |
| `user_data/strategies/EightPMHighLowStrategy.py` | Freqtrade策略 | ✅ 生产环境使用 |

### 配置文件

| 文件 | 用途 |
|------|------|
| `config/eightpm_backtest.json` | 回测专用配置 |
| `config/base.json` | 基础交易配置 |
| `requirements.txt` | Python依赖包 |

### 脚本工具

#### 本地脚本 (`scripts/local/`)
- **test_strategy.py** - 🆕新手推荐，5分钟快速测试
- **run_local_backtest.sh** - 本地快速回测
- **run_freqtrade_backtest.sh** - 完整Freqtrade回测
- **run_strategy.py** - 简化的运行入口

#### CI/CD脚本 (`scripts/ci/`)
- **prepare_backtest.sh** - GitHub Actions环境准备
- **analyze_results.sh** - 自动化结果分析

## 🚀 使用路径

### 新手用户
```
README.md → QUICKSTART.md → scripts/local/test_strategy.py
```

### 进阶用户
```
README.md → scripts/local/run_local_backtest.sh → 参数调优
```

### 开发者
```
README.md → .github/workflows/ → 自动化集成
```

## 📦 依赖关系

### 独立策略 (`scripts/local/final_optimized_strategy.py`)
```
pandas + numpy → 运行策略测试
```

### Freqtrade策略
```
freqtrade → 完整回测和交易
```

### GitHub Actions
```
ubuntu-latest + freqtrade + jq → 自动化回测
```

## 🔄 文件生命周期

### 开发阶段
1. 编辑 `scripts/local/final_optimized_strategy.py`
2. 运行 `scripts/local/test_strategy.py` 测试
3. 同步到 `user_data/strategies/EightPMHighLowStrategy.py`

### 测试阶段
1. 本地回测：`scripts/local/run_local_backtest.sh`
2. CI回测：GitHub Actions自动触发
3. 结果分析：`scripts/ci/analyze_results.sh`

### 部署阶段
1. 配置 `config/eightpm_backtest.json`
2. 运行生产回测
3. 实盘部署（需额外配置）

## 🗂️ 数据流向

```
历史数据下载 → user_data/data/
     ↓
策略回测 → user_data/backtest_results/
     ↓
结果分析 → GitHub Actions报告
```

## 🔧 维护指南

### 添加新策略版本
1. 开发新版本
2. 测试验证
3. 移动旧版本到 `strategies_archive/`
4. 更新 `strategies_archive/README.md`

### 更新文档
1. 修改相关 `.md` 文件
2. 确保链接正确
3. 更新版本信息

### 脚本维护
1. 测试所有脚本功能
2. 更新依赖版本
3. 检查路径引用

## 🎯 最佳实践

### 文件命名
- 使用描述性名称
- 版本号清晰标识
- 避免特殊字符

### 目录组织
- 按功能分类
- 保持结构扁平
- 避免深层嵌套

### 文档维护
- 及时更新说明
- 保持链接有效
- 提供使用示例

---

这个结构设计的目标是：
- 🎯 **新手友好** - 清晰的入门路径
- 🔧 **开发高效** - 完整的工具链
- 📈 **可扩展** - 易于添加新功能
- 🤖 **自动化** - CI/CD集成