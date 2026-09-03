# 0C-P8 host R1 review boundary

The R1 review boundary is intentionally narrow:

- `src/ywd1278/service/tnc_runtime.py`: replace unbounded zero-seeking RX drain
  with a four-read hardware-derived bounded pass;
- `tests/sustained_live_fifo_drain_regression_test.py`: model continuous sample
  production and partial-read termination;
- `tests/sustained_kiss_tnc_contract_test.py`: lock the corrected architecture;
- additive R1 qualification/evidence documentation and CI only.

No P7 admission, P6 control, P4e lifecycle, P5 TXDELAY, TX broker, Bell-202 TX,
firmware, daemon or systemd product-TX implementation is changed by R1.
