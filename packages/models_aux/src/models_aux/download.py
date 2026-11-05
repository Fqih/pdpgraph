# SPDX-License-Identifier: Apache-2.0
"""`make models-download`: fetch the pinned model files into the cache directory.

This is the only code path that downloads; the service runs with HF_HUB_OFFLINE=1.
"""

from huggingface_hub import snapshot_download

from models_aux.settings import ModelsAuxSettings


def download_all(settings: ModelsAuxSettings) -> None:
    for task, spec in settings.models.items():
        print(f"{task}: {spec.repo}@{spec.revision[:12]} ({spec.license})", flush=True)
        snapshot_download(
            repo_id=spec.repo,
            revision=spec.revision,
            allow_patterns=spec.allow_patterns,
            cache_dir=settings.cache_dir,
        )


if __name__ == "__main__":
    download_all(ModelsAuxSettings())
