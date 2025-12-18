# Freqtrade Render CI

用途：

- 在 Render 上自动运行 Freqtrade 回测
- 用于策略验证 / 筛选
- 不用于实盘交易

流程：

1. Push 策略代码
2. Render Background Worker 启动
3. 自动下载数据 + 回测
4. 控制台输出结果
