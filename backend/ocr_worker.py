"""Private line-protocol worker that keeps PaddleOCR warm for one verification."""
from __future__ import annotations

import json
import sys

from paddleocr import PaddleOCR


MARKER = "__BELGEDOGRULA_OCR__"


def respond(payload: dict) -> None:
    print(f"{MARKER}{json.dumps(payload, ensure_ascii=False)}", flush=True)


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    device, engine, version = sys.argv[1:]
    try:
        model = PaddleOCR(
            lang="tr",
            ocr_version=version,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
            engine=engine,
        )
    except Exception as exc:
        respond({"ok": False, "error": f"model_init:{type(exc).__name__}"})
        return 1

    for raw_request in sys.stdin:
        try:
            request = json.loads(raw_request)
            if request.get("command") == "close":
                model.close()
                respond({"ok": True, "closed": True})
                return 0
            paths = request.get("paths") or []
            results = model.predict(paths)
            pages = [result.json for result in results]
            respond({"ok": True, "pages": pages})
        except Exception as exc:
            respond({"ok": False, "error": f"predict:{type(exc).__name__}"})
    model.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
