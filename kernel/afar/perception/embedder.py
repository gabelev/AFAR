"""Audio embedders behind one protocol — the swappable seam.

The Suno-access layer and the representation model WILL change (the spec calls
the ingestion brittle by design), so everything downstream depends only on
`AudioEmbedder`. Real MERT/CLAP embedders slot in behind it; the bench and the
clusterer never know.
"""

# ported from mold (moldzine/mold/mold/perception/embedder.py)

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class AudioEmbedder(Protocol):
    """One track file in (read transiently), one embedding vector out.

    Implementations MUST NOT retain or copy the audio — derived features only.
    """

    name: str
    dim: int

    def embed(self, path: Path) -> list[float]: ...


class MockEmbedder:
    """Deterministic pseudo-embeddings from file bytes. Zero deps, zero GPU.

    Chunk-mean features: the file is split into `dim` chunks and each dimension
    is that chunk's mean byte value. Locality-preserving (similar bytes ->
    nearby vectors), which is meaningless musically — this proves plumbing,
    not the hypothesis. Swap in MERT for the real Phase 0 test.
    """

    name = "mock"
    dim = 16

    def embed(self, path: Path) -> list[float]:
        data = path.read_bytes() or b"\x00"
        chunk = max(1, len(data) // self.dim)
        vec = []
        for i in range(self.dim):
            piece = data[i * chunk:(i + 1) * chunk] or data[-chunk:]
            vec.append(sum(piece) / (len(piece) * 255.0))
        return vec


class MERTEmbedder:
    """MERT self-supervised music representation (the spec's primary space).

    Requires the `listen` extra:  uv sync --extra listen
    Fetch audio transiently, embed, DISCARD the waveform; persist only the
    vector + metadata + the source link.

    Representation: time-mean over the mean of all transformer layers —
    different MERT layers carry different musical information (model card),
    so averaging layers is the robust unsupervised default for clustering.
    """

    name = "mert"
    dim = 768

    def __init__(
        self,
        model_id: str = "m-a-p/MERT-v1-95M",
        *,
        device: str | None = None,
        max_seconds: float = 60.0,
    ) -> None:
        try:
            import torch
            from transformers import AutoModel, Wav2Vec2FeatureExtractor
        except ImportError as e:
            raise ImportError(
                "MERTEmbedder needs the listen extra: uv sync --extra listen"
            ) from e
        self.model_id = model_id
        self.max_seconds = max_seconds
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(
            model_id, trust_remote_code=True
        )
        self.model = (
            AutoModel.from_pretrained(model_id, trust_remote_code=True)
            .to(self.device)
            .eval()
        )
        self.sample_rate = int(self.processor.sampling_rate)  # 24 kHz for MERT-v1

    def embed(self, path: Path) -> list[float]:
        import librosa
        import torch

        # Transient read: decoded, resampled, embedded, discarded.
        wav, _ = librosa.load(
            path, sr=self.sample_rate, mono=True, duration=self.max_seconds
        )
        inputs = self.processor(
            wav, sampling_rate=self.sample_rate, return_tensors="pt"
        ).to(self.device)
        with torch.no_grad():
            out = self.model(**inputs, output_hidden_states=True)
        # [n_layers+1, batch, time, 768] -> mean over layers, then time.
        stacked = torch.stack(out.hidden_states)
        vec = stacked.mean(dim=0).mean(dim=1).squeeze(0)
        return vec.float().cpu().tolist()
