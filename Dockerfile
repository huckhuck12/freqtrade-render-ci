FROM freqtradeorg/freqtrade:stable

WORKDIR /freqtrade

COPY user_data ./user_data
COPY config ./config
COPY scripts ./scripts

RUN chmod +x ./scripts/ci/prepare_backtest.sh
RUN chmod +x ./scripts/local/run_local_backtest.sh

CMD ["./scripts/ci/prepare_backtest.sh"]
