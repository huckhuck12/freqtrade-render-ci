#!/bin/bash
set -e

echo "=== Download data ==="
freqtrade download-data \
  --config config/backtest.json \
  --timeframes 5m 15m

echo "=== Run backtesting ==="
freqtrade backtesting \
  --config config/backtest.json \
  --strategy OneFiveTrendHTF \
  --export trades \
  --export-filename /tmp/result.json

echo "=== Backtest Result ==="
cat /tmp/result.json
