# Third-party AASIST architecture

`aasist.py`, configuration and MIT license originate from NAVER/clovaai AASIST,
commit `a04c9863f63d44471dde8a6abcb3b082b07cd1d1`:
https://github.com/clovaai/aasist/tree/a04c9863f63d44471dde8a6abcb3b082b07cd1d1

The architecture is executed locally; no remote model code is loaded at runtime.
The checkpoint is downloaded separately to ignored `models/aasist.pth`; SHA256
`51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0`.
Upstream code is retained, with import formatting only. It is excluded from
first-party coverage; integrity wrappers remain included.

Face PAD uses MiniFASNetV2 ONNX, pinned Hugging Face revision
`d29c87568ca9b5662da803b10f217c4db20b142b`, Apache 2.0:
https://huggingface.co/garciafido/minifasnet-v2-anti-spoofing-onnx
The upstream training/inference code defines live class **1** and BGR float
input in **[0,255]** (`functional.to_tensor`, `test.py` at
`minivision-ai/Silent-Face-Anti-Spoofing@b6d5f04ad78778917853b25c778acef6d5626d15`).
Those authoritative conventions override the converter model card's conflicting
class-order/scaling text. Do not silently adopt the model card's index 0 or /255.

Research detector outputs are not verified probabilities of cheating. No local
anti-spoof ground-truth benchmark has been substituted with synthetic evidence.
