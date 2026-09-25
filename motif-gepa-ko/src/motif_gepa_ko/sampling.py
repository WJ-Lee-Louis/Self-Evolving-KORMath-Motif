"""Deterministic difficulty-stratified minibatches for HRM8K Omni-MATH."""

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
from math import ceil

from gepa.core.data_loader import DataLoader
from gepa.core.state import GEPAState


BIN_QUOTAS = {
    "low_lt_3_5": 1,
    "middle_3_5_to_6_0": 3,
    "high_gt_6_0": 1,
}
SAMPLER_NAME = "omni_difficulty_1_3_1"
SAMPLER_VERSION = 1


def expected_bin(value: str) -> str:
    try:
        difficulty = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid difficulty: {value!r}") from exc
    if not difficulty.is_finite():
        raise ValueError(f"Invalid difficulty: {value!r}")
    if difficulty < Decimal("3.5"):
        return "low_lt_3_5"
    if difficulty <= Decimal("6.0"):
        return "middle_3_5_to_6_0"
    return "high_gt_6_0"


class OmniStratifiedBatchSampler:
    """One low, three middle, one high example per GEPA reflective iteration.

    Each bin gets an independent deterministic permutation per epoch. Positions
    are derived from GEPA's saved iteration counter, so a resumed process
    produces the same next batch without serializing sampler-local RNG state.
    This project uses GEPA's default single-mutation proposal strategy.
    """

    def __init__(self, train_records: list[dict], seed: int):
        self.seed = seed
        self.ids_by_bin: dict[str, list[int]] = {name: [] for name in BIN_QUOTAS}
        for position, record in enumerate(train_records):
            if record.get("source_subset") != "OMNI-MATH":
                raise ValueError(f"Non-Omni train row at position {position}")
            difficulty_bin = record.get("difficulty_bin")
            if difficulty_bin != expected_bin(str(record.get("difficulty"))):
                raise ValueError(f"Difficulty bin mismatch at position {position}")
            self.ids_by_bin[difficulty_bin].append(position)
        for name, quota in BIN_QUOTAS.items():
            if len(self.ids_by_bin[name]) < quota:
                raise ValueError(f"Too few {name} rows for a {quota}-item quota")
        self._permutations: dict[tuple[str, int], list[int]] = {}

    def describe(self) -> dict:
        return {
            "name": SAMPLER_NAME,
            "version": SAMPLER_VERSION,
            "seed": self.seed,
            "quotas": dict(BIN_QUOTAS),
            "pool_counts": {name: len(ids) for name, ids in self.ids_by_bin.items()},
            "rule": "SHA-256 order per difficulty bin and epoch; repeat only after bin epoch, with minimal end padding",
        }

    def _permutation(self, name: str, epoch: int) -> list[int]:
        key = (name, epoch)
        if key not in self._permutations:
            # Keep only the current epoch per bin. Ordering depends on stable
            # hashes rather than Python's process-randomized hash().
            self._permutations = {
                cache_key: permutation
                for cache_key, permutation in self._permutations.items()
                if cache_key[0] != name
            }
            self._permutations[key] = sorted(
                self.ids_by_bin[name],
                key=lambda position: (
                    hashlib.sha256(f"{self.seed}|{name}|{epoch}|{position}".encode()).digest(),
                    position,
                ),
            )
        return self._permutations[key]

    def next_minibatch_ids(self, loader: DataLoader, state: GEPAState) -> list[int]:
        if list(loader.all_ids()) != list(range(sum(map(len, self.ids_by_bin.values())))):
            raise ValueError("Omni sampler requires the unchanged list-backed trainset order")
        # GEPA initializes state.i at -1 and increments it before the first
        # reflective proposal, so the first sampled batch has state.i == 0.
        iteration = int(state.i)
        if iteration < 0 or iteration != state.i:
            raise ValueError(f"Invalid GEPA iteration: {state.i}")
        selected = []
        for name, quota in BIN_QUOTAS.items():
            pool_size = len(self.ids_by_bin[name])
            batches_per_epoch = ceil(pool_size / quota)
            epoch, batch_index = divmod(iteration, batches_per_epoch)
            ordered = self._permutation(name, epoch)
            padding = (-pool_size) % quota
            padded = ordered + ordered[:padding]
            selected.extend(padded[batch_index * quota:(batch_index + 1) * quota])
        if len(selected) != 5 or len(set(selected)) != 5:
            raise RuntimeError("Stratified sampler produced an incomplete or duplicate minibatch")
        return sorted(
            selected,
            key=lambda position: hashlib.sha256(
                f"{self.seed}|batch|{iteration}|{position}".encode()
            ).digest(),
        )


def batch_bin_counts(indices: list[int], train_records: list[dict]) -> dict[str, int]:
    return dict(Counter(train_records[index]["difficulty_bin"] for index in indices))
