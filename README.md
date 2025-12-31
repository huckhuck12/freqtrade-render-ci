# Freqtrade 8PM High/Low Strategy

一个基于"大道至简"理念的量化交易策略，通过识别晚上8点的日内极值点进行反转交易。

## 🎯 策略概述

### 核心逻辑
- **时间节点**: 以晚上8点(20:00)为关键判断时间
- **极值识别**: 判断8点K线是否为当日最高点或最低点
- **交易方向**: 8点最高点做空，8点最低点做多
- **确认机制**: 等待价格确认反转后入场

### 优化特性
- ✅ **高胜率**: 58.10%胜率
- 📈 **稳定收益**: 年化收益率9.42%
- 🛡️ **风险控制**: 1.5%止损，3.0%止盈
- 🔍 **智能过滤**: 成交量确认 + 趋势过滤

## 📊 回测表现

| 指标 | 数值 |
|------|------|
| 总收益率 | 47.12% (5年) |
| 年化收益率 | 9.42% |
| 胜率 | 58.10% |
| 止盈率 | 58.10% |
| 总交易次数 | 253笔 |
| 盈亏比 | 2:1 |

## 🚀 快速开始

**🎯 [点击这里查看详细的快速开始指南](QUICKSTART.md)**

### 三种使用方式

| 方式 | 适合人群 | 时间 | 特点 |
|------|----------|------|------|
| [独立测试](QUICKSTART.md#方式一独立测试-5分钟-) | 🆕 新手 | 5分钟 | 无需复杂配置 |
| [本地回测](QUICKSTART.md#方式二本地回测-15分钟-) | 🔧 进阶用户 | 15分钟 | 真实数据回测 |
| [GitHub Actions](QUICKSTART.md#方式三github-actions-自动化-) | 🤖 开发者 | 自动化 | 持续集成 |

### 方式一：本地独立测试（推荐新手）

不需要安装freqtrade，使用模拟数据快速验证策略：

```bash
# 克隆仓库
git clone <repository-url>
cd freqtrade-render-ci

# 安装依赖
pip install pandas numpy matplotlib

# 运行独立测试
python scripts/local/test_strategy.py
```

### 方式二：本地freqtrade回测

需要安装freqtrade环境：

```bash
# 安装freqtrade
pip install freqtrade

# 运行本地回测（使用默认参数）
chmod +x scripts/local/run_local_backtest.sh
./scripts/local/run_local_backtest.sh

# 自定义参数回测
./scripts/local/run_local_backtest.sh 20240101-20241231 "ETH/USDT BTC/USDT" 365
```

### 方式三：GitHub Actions自动回测

1. Fork这个仓库
2. 创建Pull Request或推送到main分支
3. 自动触发回测并在PR中显示结果

手动触发回测：
1. 进入Actions页面
2. 选择"Manual Backtest - 8PM Strategy"
3. 点击"Run workflow"并设置参数

## 📁 项目结构

```
freqtrade-render-ci/
├── user_data/
│   └── strategies/
│       └── EightPMHighLowStrategy.py    # 主策略文件
├── config/
│   ├── eightpm_backtest.json           # 回测配置
│   └── base.json                       # 基础配置
├── scripts/
│   ├── local/                          # 本地脚本
│   │   ├── run_local_backtest.sh       # 本地回测脚本
│   │   ├── test_strategy.py            # 独立策略测试
│   │   └── run_freqtrade_backtest.sh   # Freqtrade回测
│   └── ci/                             # CI/CD脚本
│       ├── prepare_backtest.sh         # 回测准备
│       └── analyze_results.sh          # 结果分析
├── .github/workflows/
│   ├── backtest.yml                    # 自动回测
│   └── manual-backtest.yml             # 手动回测
├── final_optimized_strategy.py         # 已移动到 scripts/local/
├── STRATEGY_README.md                  # 详细策略说明
└── README.md                           # 项目说明
```

## 🔧 策略参数

### 核心参数
```python
timeframe = "1h"              # 时间框架
stoploss = -0.015             # 止损 1.5%
minimal_roi = {"0": 0.03}     # 止盈 3.0%
```

### 过滤参数
```python
volume_threshold = 1.1        # 成交量阈值
confirmation_threshold = 0.001 # 价格确认阈值 0.1%
tolerance = 0.005             # 极值容差 0.5%
sma_range_pct = 0.05          # 均线范围 5%
```

## 📈 使用场景

### 适合的市场环境
- ✅ 震荡市场
- ✅ 中等波动率市场
- ✅ 有明显日内节奏的市场

### 不适合的市场环境
- ❌ 极端单边趋势市场
- ❌ 超低波动率市场
- ❌ 异常高波动率市场

## ⚠️ 风险提示

1. **历史表现不代表未来**: 回测结果基于历史数据
2. **市场环境变化**: 策略表现可能因市场环境而异
3. **实盘差异**: 需考虑滑点、手续费等实际成本
4. **资金管理**: 建议仓位不超过总资金的10%

## 🛠️ 自定义和优化

### 参数调优
可以修改以下文件中的参数：
- `user_data/strategies/EightPMHighLowStrategy.py` - Freqtrade策略
- `scripts/local/final_optimized_strategy.py` - 独立策略实现

### 常见调优方向
1. **调整止损止盈比例**
2. **修改成交量阈值**
3. **优化价格确认机制**
4. **添加额外过滤条件**

## 📚 相关文档

- [详细策略说明](STRATEGY_README.md)
- [Freqtrade官方文档](https://www.freqtrade.io/)
- [策略开发指南](https://www.freqtrade.io/en/stable/strategy-customization/)

## 🤝 贡献

欢迎提交Issue和Pull Request来改进策略！

### 贡献方式
1. Fork项目
2. 创建特性分支
3. 提交更改
4. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 查看[LICENSE](LICENSE)文件了解详情。

## ⭐ 支持项目

如果这个策略对你有帮助，请给项目点个星！

---

**免责声明**: 本策略仅供学习和研究使用，不构成投资建议。交易有风险，投资需谨慎。
