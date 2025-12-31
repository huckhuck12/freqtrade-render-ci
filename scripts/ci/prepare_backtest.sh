#!/bin/bash
# GitHub Actions 回测准备脚本

set -e

echo "=== CI环境回测准备 ==="

# 检查必要的环境变量
if [ -z "$GITHUB_WORKSPACE" ]; then
    echo "⚠️  非GitHub Actions环境"
else
    echo "✅ GitHub Actions环境检测"
    echo "📁 工作目录: $GITHUB_WORKSPACE"
fi

# 显示freqtrade版本
echo "🔧 Freqtrade版本:"
freqtrade --version

# 检查配置文件
if [ -f "config/eightpm_backtest.json" ]; then
    echo "✅ 配置文件存在"
else
    echo "❌ 配置文件不存在: config/eightpm_backtest.json"
    exit 1
fi

# 检查策略文件
if [ -f "user_data/strategies/EightPMHighLowStrategy.py" ]; then
    echo "✅ 策略文件存在"
else
    echo "❌ 策略文件不存在: user_data/strategies/EightPMHighLowStrategy.py"
    exit 1
fi

# 创建必要的目录
mkdir -p user_data/data
mkdir -p user_data/backtest_results
mkdir -p user_data/logs

echo "✅ 环境准备完成"