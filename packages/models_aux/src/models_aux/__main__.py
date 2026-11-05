# SPDX-License-Identifier: Apache-2.0
"""`python -m models_aux`: load the pinned models from the local cache and serve on port 8070."""

import os

import uvicorn

from common.logging import configure_logging
from models_aux.app import create_app
from models_aux.models import load_models
from models_aux.settings import ModelsAuxSettings


def require_offline() -> None:
    """The service must never download models on its own (M0.4)."""
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise SystemExit("models-aux must run with HF_HUB_OFFLINE=1; use `make models-download`")


def main() -> None:
    require_offline()
    configure_logging("models-aux")
    settings = ModelsAuxSettings()
    app = create_app(load_models(settings), settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
