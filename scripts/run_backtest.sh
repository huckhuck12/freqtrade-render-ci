#!/bin/bash
set -e

echo "=== Download data ==="
freqtrade download-data \
  --config config/backtest.json \
  --timeframes 1m 5m 15m \
  --pairs BTC/USDT ETH/USDT ETH/BTC SOL/USDT AVAX/USDT NEAR/USDT OP/USDT ARB/USDT

echo "=== Run backtesting ==="
freqtrade backtesting \
  --config config/backtest.json \
  --strategy SimplifiedArbitrage \
  --export trades \
  --export-filename /tmp/result.json

echo "=== Backtest Result ==="
cat /tmp/result.json
