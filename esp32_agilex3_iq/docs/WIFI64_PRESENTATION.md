# Native Wi-Fi RF story

Open `/story` on the native Wi-Fi display service (default port8774).
The narrow view uses the same qualified raw-IQ proof as `/`, with no hardware
operations or host receiver DSP. The illustration is
[wifi64_phy.svg](images/wifi64_phy.svg).

Three panels intentionally show different kinds of evidence:

1. **TX alphabet:** all64 ideal points, a reference diagram only. This is neither
   measured TX IQ nor reconstruction of this packet's exact transmitted symbols.
2. **RX:** actual Nios-exported equalized DATA points from the RF packet.
3. **FEC:** actual decoded packet bytes as a bit matrix, after Viterbi and
   descrambling. Color represents bit value, not error/correction status.

The existing proof has no exported PHY scrambler seed or before/after error
counters. Payload generator seed and PHY scrambler seed are different quantities.
Do not infer BER from a passing FCS or snap RX points to a grid and call it FEC.
An exact post-FEC constellation requires on-device re-encoding, puncturing,
interleaving and mapping of the recovered frame, plus explicit provenance and
same-symbol alignment. It would be labeled **re-encoded/remapped**, not received
IQ. That export is not implemented by this presentation change.

We choose packet bytes within the native frame API and our firmware's current
known-pattern generator. The ESP32's Wi-Fi PHY constructs its standardized coded
OFDM waveform. Arbitrary user-defined QAM symbol sequences or IQ samples bypassing
that PHY are a separate feature. They are unproven on our original ESP32 radios.
The published [IQ TX project](https://github.com/whstudio123/esp32-iq-tx) targets
ESP32-S3/S31; this is not evidence of original-chip support or our own 64-QAM RF
qualification on those chips. See the [custom TX plan](CUSTOM_IQ_64QAM_OTA_PLAN.md).

Current decode is Nios software inside Agilex3, including FIR. RTL provides
capture RAM and transport. The saved successful packet took150.3seconds; the
page polls saved evidence and is not continuous live RF acquisition.
