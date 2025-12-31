#!/bin/bash
# GitHub Actions 结果分析脚本

set -e

echo "=== 分析回测结果 ==="

# 查找最新的结果文件
RESULTS_DIR="user_data/backtest_results"
ZIP_FILE=$(ls -t "$RESULTS_DIR"/*.zip 2>/dev/null | head -n 1)

if [ -z "$ZIP_FILE" ]; then
    echo "❌ 未找到回测结果文件"
    exit 1
fi

echo "📁 结果文件: $ZIP_FILE"

# 解压结果
TEMP_DIR="/tmp/backtest_analysis"
mkdir -p "$TEMP_DIR"
unzip -o "$ZIP_FILE" -d "$TEMP_DIR"

echo "📂 解压文件:"
ls -la "$TEMP_DIR"

# 查找JSON结果文件
JSON_FILE=$(find "$TEMP_DIR" -name "*.json" | head -n 1)

if [ -z "$JSON_FILE" ]; then
    echo "❌ 未找到JSON结果文件"
    exit 1
fi

echo "📊 分析文件: $JSON_FILE"

# 检查jq是否可用
if ! command -v jq &> /dev/null; then
    echo "❌ jq工具未安装"
    exit 1
fi

# 提取关键指标
PROFIT=$(jq -r '.strategy_comparison[0].profit_total_pct // "N/A"' "$JSON_FILE")
WINRATE=$(jq -r '.strategy_comparison[0].winrate // "N/A"' "$JSON_FILE")
TRADES=$(jq -r '.strategy_comparison[0].trades // "N/A"' "$JSON_FILE")
DRAWDOWN=$(jq -r '.strategy_comparison[0].max_drawdown_account // "N/A"' "$JSON_FILE")
PROFIT_FACTOR=$(jq -r '.strategy_comparison[0].profit_factor // "N/A"' "$JSON_FILE")
EXPECTANCY=$(jq -r '.strategy_comparison[0].expectancy // "N/A"' "$JSON_FILE")
WINS=$(jq -r '.strategy_comparison[0].wins // "N/A"' "$JSON_FILE")
LOSSES=$(jq -r '.strategy_comparison[0].losses // "N/A"' "$JSON_FILE")

# 输出结果到环境变量（用于GitHub Actions）
{
    echo "BACKTEST_PROFIT=$PROFIT"
    echo "BACKTEST_WINRATE=$WINRATE"
    echo "BACKTEST_TRADES=$TRADES"
    echo "BACKTEST_DRAWDOWN=$DRAWDOWN"
    echo "BACKTEST_PROFIT_FACTOR=$PROFIT_FACTOR"
    echo "BACKTEST_EXPECTANCY=$EXPECTANCY"
    echo "BACKTEST_WINS=$WINS"
    echo "BACKTEST_LOSSES=$LOSSES"
} >> "$GITHUB_ENV"

# 显示结果摘要
echo ""
echo "=== 回测结果摘要 ==="
echo "💰 总收益: $PROFIT%"
echo "📈 胜率: $WINRATE%"
echo "🔁 交易次数: $TRADES"
echo "✅ 盈利交易: $WINS"
echo "❌ 亏损交易: $LOSSES"
echo "📉 最大回撤: $DRAWDOWN%"
echo "🎲 盈利因子: $PROFIT_FACTOR"
echo "💡 期望值: $EXPECTANCY"

# 性能评估
echo ""
echo "=== 性能评估 ==="

# 胜率评估
if [ "$WINRATE" != "N/A" ]; then
    if (( $(echo "$WINRATE >= 55" | bc -l) )); then
        echo "✅ 胜率优秀 (>= 55%)"
    elif (( $(echo "$WINRATE >= 45" | bc -l) )); then
        echo "⚠️  胜率一般 (45-55%)"
    else
        echo "❌ 胜率偏低 (< 45%)"
    fi
fi

# 盈利因子评估
if [ "$PROFIT_FACTOR" != "N/A" ]; then
    if (( $(echo "$PROFIT_FACTOR >= 1.5" | bc -l) )); then
        echo "✅ 盈利因子良好 (>= 1.5)"
    elif (( $(echo "$PROFIT_FACTOR >= 1.0" | bc -l) )); then
        echo "⚠️  盈利因子一般 (1.0-1.5)"
    else
        echo "❌ 盈利因子不佳 (< 1.0)"
    fi
fi

echo "✅ 结果分析完成"