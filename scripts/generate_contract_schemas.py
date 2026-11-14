import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.contract_schemas import CONTRACT_MODELS

OUTPUT_DIRECTORY = ROOT / "backend" / "app" / "schemas" / "generated"


def generate() -> None:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    expected = set()
    for name, model in sorted(CONTRACT_MODELS.items()):
        target = OUTPUT_DIRECTORY / f"{name}.json"
        target.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        expected.add(target.name)
    for stale in OUTPUT_DIRECTORY.glob("*.json"):
        if stale.name not in expected:
            stale.unlink()


if __name__ == "__main__":
    generate()
