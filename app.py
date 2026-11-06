"""Local-only entry point. Run with an existing TTS virtual environment."""
from pathlib import Path
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os

ROOT = Path(__file__).resolve().parent
for key, value in {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "GRADIO_ANALYTICS_ENABLED": "False"}.items():
    os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description="Local Qwen3-TTS workspace")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local")
    parser.add_argument("--models-root", type=Path, action="append")
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535")
    from studio.instance import InstanceLock
    from studio.privacy import PrivateFormatter
    data = args.data_dir.resolve()
    instance = InstanceLock(data)
    try:
        (data / "logs").mkdir(parents=True, exist_ok=True)
        formatter = PrivateFormatter("%(asctime)s %(levelname)s %(message)s")
        handlers = [RotatingFileHandler(data / "logs" / "studio.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"), logging.StreamHandler()]
        for handler in handlers:
            handler.setFormatter(formatter)
        logging.basicConfig(level=logging.INFO, handlers=handlers)
        from studio.server import create_app
        app = create_app(ROOT, data, args.models_root)
        if args.model:
            app.state.registry.register(str(args.model))
        import uvicorn
        print(f"Qwen Voice Studio: http://127.0.0.1:{args.port}")
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_config=None, limit_concurrency=32, timeout_keep_alive=5)
    finally:
        instance.close()


if __name__ == "__main__":
    main()
