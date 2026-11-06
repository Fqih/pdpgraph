# SPDX-License-Identifier: Apache-2.0
"""`make models-download`: fetch the pinned model files into the cache directory.

This is the only code path that downloads; the service runs with HF_HUB_OFFLINE=1. Pickled
files listed under `convert` are converted to safetensors here, once (ADR-020); the service only
loads the converted file.
"""

from pathlib import Path

from huggingface_hub import snapshot_download

from models_aux.convert import convert_to_safetensors, converted_dir
from models_aux.settings import ModelsAuxSettings


def download_all(settings: ModelsAuxSettings) -> None:
    for task, spec in settings.models.items():
        print(f"{task}: {spec.repo}@{spec.revision[:12]} ({spec.license})", flush=True)
        snapshot = Path(
            snapshot_download(
                repo_id=spec.repo,
                revision=spec.revision,
                allow_patterns=spec.allow_patterns,
                cache_dir=settings.cache_dir,
            )
        )
        out_dir = converted_dir(settings.cache_dir, spec.repo, spec.revision)
        for name, conv in spec.convert.items():
            out = out_dir / conv.output
            digest = convert_to_safetensors(snapshot / name, conv.sha256, out)
            if digest != conv.output_sha256:
                out.unlink()
                raise SystemExit(
                    f"{name} -> {conv.output}: sha256 {digest} is not the pinned "
                    f"{conv.output_sha256}"
                )
            print(f"  converted {name} -> {out}", flush=True)


if __name__ == "__main__":
    download_all(ModelsAuxSettings())
