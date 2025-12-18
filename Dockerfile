FROM freqtradeorg/freqtrade:stable

WORKDIR /freqtrade

COPY strategies ./strategies
COPY config ./config
COPY scripts ./scripts

RUN chmod +x ./scripts/run_backtest.sh

CMD ["./scripts/run_backtest.sh"]
