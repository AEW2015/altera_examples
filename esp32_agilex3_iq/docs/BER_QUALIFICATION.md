# BER qualification: repeatable simulation and saved RF audit

This workflow keeps seeded symbol-level AWGN experiments separate from physical BPSK and QPSK evidence. It compares hard and soft Viterbi decoding on the same noisy coded samples, reports uncoded and coded counts, and audits saved RF proof files without opening hardware.

## Command line

Run a reproducible 1,000-frame sweep with 16 payload bytes per frame at the listed Eb/N0 values:

```bash
.venv-notebooks/bin/python scripts/check_rf_ber.py \
  --output cyberether/run/ber-qualification \
  --frames 1000 --payload-bytes 16 --seed 20261021 \
  --ebn0 0 2 4 6
```

The command writes `qualification.json`. Each simulated point has 128,000 payload bits and 136,000 encoder-information bits (payload plus CRC) across 1,000 independent frames. The K=7 rate-1/2 code includes six tail bits. Eb/N0 is normalized per encoder-information bit; preamble and guard overhead are excluded. Synchronization is perfect in this experiment, so it does not exercise RF acquisition, timing, carrier recovery, FPGA execution or transmitter behavior.

To include a saved-RF audit, pass one or more BPSK and/or QPSK proof files. The script never captures RF. Use `--rf-only` to skip the synthetic sweep:

```bash
.venv-notebooks/bin/python scripts/check_rf_ber.py \
  --output cyberether/run/ber-rf-audit --rf-only \
  --proof cyberether/run/rf-bpsk-001/proof.json \
  --proof cyberether/run/rf-bpsk-002/proof.json
```

The CLI writes separate `rf` (BPSK) and `rf_qpsk` evidence sections. Each audit accepts only proofs of its named physical modulation, deduplicates raw captures by CI8 SHA-256, preserves receiver/settings groups, counts synchronized CRC-failed frames in BER, and reports acquisition failures separately. Setting groups retain modulation, payload, receiver/source, channel, backoff, gain, symbol period and pulse widths. It recomputes hard decisions from saved soft metrics for a paired hard/soft comparison; it audits saved reports and does not re-decode raw IQ. With no known payload reference, it reports CRC/acquisition counts and marks BER as unreferenced. `--reference-payload 0xA5` can override the configured reference when appropriate.

Both branches can be written to one output file:

```bash
.venv-notebooks/bin/python scripts/check_rf_ber.py \
  --output cyberether/run/ber-combined --frames 1000 --payload-bytes 16 \
  --ebn0 0 2 4 6 \
  --proof cyberether/run/rf-bpsk-001/proof.json
```

The Python API is in `cyberether/ber_qualification.py`:

- `run_sweep(ebn0_db, frames=100, payload_bytes=16, seed=20261021, confidence=.95, progress=None)` returns the deterministic synthetic result structure.
- `aggregate_rf(proof_paths, reference_payload=None, confidence=.95, modulation='BPSK')` audits saved proof paths for one modulation only; use `modulation='QPSK'` for QPSK proofs.
- `error_metric(errors, trials, confidence=.95)` returns the observed rate and, for zero errors, the exact one-sided binomial upper bound.
- `noise_sigma(ebn0_db, information_bits, coded_bits)` computes the real AWGN standard deviation under the module's Es=1 normalization.

## Measured results and interpretation

The fixed 1,000-frame, 16-byte simulation produced 704 hard-decision payload errors and 8 soft-decision payload errors at 4 dB, both over the same 128,000 payload bits. At 6 dB soft decoding observed zero errors. Its one-sided 95% bit-error upper bound is **2.3404 × 10⁻⁵**, assuming independent bit errors. Post-FEC bit errors are correlated, so also report the separate frame-error bound: zero erroneous frames among 1,000 gives an exact one-sided 95% upper bound of about **0.299%**, under an independent-frame assumption. Neither bound describes RF performance.

The historical BPSK and QPSK audit totals are preserved. The current v6 run audit is reported separately and also included in the recursive aggregate. Do not combine modulation totals or repeated settings as if they were one calibrated BER curve.

### Extended RF evidence

The v6 audit adds 172 unique captures (8 BPSK and 164 QPSK) to the 744-capture historical baseline. The recursive combined audit covers 916 unique raw captures; all passed length, CRC and SHA-256 checks and blind re-decode. Counts are grouped by modulation, payload and settings; the aggregate is not an operating-point BER curve.

|Audit scope|Modulation|Captures|Acquired frames|CRC pass / fail|No acquisition|Coded errors / bits|Payload errors / bits|
|---|---|---:|---:|---:|---:|---:|---:|
|Historical baseline|BPSK|420|441|438 / 3|0|337 / 19404|1 / 3528|
|Historical baseline|QPSK|324|163|153 / 10|161|200 / 7172|37 / 1304|
|New v6 captures|BPSK|8|9|8 / 1|—|16 / 396|0 / 72|
|New v6 captures|QPSK|164|99|90 / 9|66|206 / 4356|33 / 792|
|Historical + v6 aggregate|BPSK|428|450|446 / 4|—|353 / 19800|1 / 3600|
|Historical + v6 aggregate|QPSK|488|262|243 / 19|227|406 / 11528|70 / 2096|

BPSK and QPSK remain separate; the aggregate combines operating points and is not suitable for comparing BER by symbol period. No claim of all-zero errors or a soft-decision RF advantage follows. The v6 audit is in `cyberether/run/rf-v6-independent-audit/qualification.json`; the refreshed recursive aggregate is in `cyberether/run/ber-qualification/qualification.json`. These finite, grouped captures remain below the 100,000-payload-bit target per operating point and do not establish continuous delivery.

The earlier QPSK-002 aggregate uses the original proof's four valid frames; the later blind 54-symbol reanalysis recovered a fifth frame from the same captures but is not counted again. Empty failed QPSK configuration jobs are listed separately and add no RF bits. See [QPSK qualification](QPSK_QUALIFICATION.md) for run-level timing results.

The live page's physical-evidence panel displays BPSK totals separately from a QPSK table grouped by symbol period and payload. It shows capture/acquisition counts, CRC pass/fail counts, and coded/payload bit counts. Reprocessing captures does not add RF evidence. The BER comparison button still runs synthetic AWGN plus these saved-proof audits; it does not transmit or capture RF.

Zero observed errors are reported with the tested denominator and a stated confidence assumption, never as zero true BER. Frame-level confidence is useful when decoded bit errors cluster within a frame. Captures and frames can also be correlated across a repeated RF run; capture IDs, duplicate exclusions, settings and observation gaps remain part of the evidence.

## Live RF Link Lab

Start the local page on port 8770:

```bash
.venv-notebooks/bin/python scripts/start_rf_link_lab.py
```

Its **BER comparison** action runs the fixed 1,000-frame-per-point AWGN simulation and audits saved RF proof files under `cyberether/run/`. It does not start a transmitter or capture RF. The page labels the simulation separately and displays the results and BER plot. An actual RF capture remains a separate explicit capture action.

The page accepts `POST /api/qualify` with an empty JSON object. The server runs `scripts/check_rf_ber.py --frames 1000 --payload-bytes 16`, adds discovered saved proofs, and writes `cyberether/run/ber-qualification/qualification.json`. It uses the acquisition lock to avoid overlapping a live capture even though the qualification itself is offline.

See [RF BPSK walkthrough](RF_BPSK_WALKTHROUGH.md) for the frame format and physical capture checker, and [the modem roadmap](RF_MODEM_BPSK_TO_64QAM_PLAN.md) for staged qualification gates.
