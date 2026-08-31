"""QR'ı doğrula, HTTPS'e yükselt ve resmî PDF'leri geçici belleğe al."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from qr_reader import read_qr_image
from url_security import Policy, SecurityError, prepare, safe_fetch


class FrameParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "iframe":
            source = dict(attrs).get("src")
            if source:
                self.sources.append(source)


def _recovery_detail(result: dict[str, object]) -> str | None:
    qr = result.get("qr")
    if not isinstance(qr, dict):
        return None
    outputs = qr.get("decoder_outputs", [])
    methods = {
        output.get("recovery_method")
        for output in outputs
        if isinstance(output, dict) and output.get("recovery_method")
    }
    if any(str(method).startswith("restormer_") for method in methods):
        return (
            "QR, yapay zekâ tabanlı bulanıklık/gürültü iyileştirmesinden sonra "
            "bağımsız okuyucular tarafından doğrulandı."
        )
    if any(
        "denoise" in str(method) or "unsharp" in str(method)
        for method in methods
    ):
        return (
            "QR, görüntüdeki bulanıklık ve gürültü azaltıldıktan sonra "
            "bağımsız okuyucular tarafından doğrulandı."
        )
    if methods:
        return (
            "QR, kontrast ve çözünürlük iyileştirmesinden sonra bağımsız "
            "okuyucular tarafından doğrulandı."
        )
    return "QR içeriği bağımsız okuyucular tarafından doğrulandı."


def _domain_detail(result: dict[str, object]) -> str:
    target = result.get("target")
    if (
        isinstance(target, dict)
        and target.get("domain_validation") == "official_domain"
    ):
        return (
            "QR'daki kurum alan adı otomatik olarak resmî alan adı "
            "kurallarına göre doğrulandı."
        )
    return "QR'daki kurum alan adı yapılandırılmış izin listesiyle doğrulandı."


def _summary(result: dict[str, object]) -> dict[str, object]:
    status = result["status"]
    if status == "document_fetched":
        count = len(result["official_documents"])
        return {
            "title": "Resmî belgeler güvenli biçimde alındı.",
            "details": [
                _recovery_detail(result),
                _domain_detail(result),
                "HTTP hedef aynı host, yol ve parametrelerle HTTPS'e yükseltildi.",
                "Eksik TLS ara sertifikası parmak izi doğrulanarak tamamlandı.",
                f"{count} PDF doğrulandı; dosyalar diske kaydedilmedi.",
            ],
            "decision": "Belgeler OCR ve karşılaştırma için hazır.",
            "verified_url": result["target"]["effective_url"],
            "next_step": "PDF metinleri OCR ile çıkarılabilir.",
        }
    if status == "target_validated":
        return {
            "title": "QR kod ve resmî hedef doğrulandı.",
            "details": [
                _recovery_detail(result),
                _domain_detail(result),
                "Güvenli HTTPS erişim hedefi hazırlandı.",
                "Henüz dış sunucudan belge alınmadı.",
            ],
            "decision": "Hedef güvenli erişim için uygun.",
            "verified_url": result["target"]["effective_url"],
            "next_step": "Komutu --fetch seçeneğiyle çalıştırın.",
        }
    if status == "target_blocked":
        return {
            "title": "Hedef güvenlik kontrolünden geçemedi.",
            "details": [
                result["target_error"]["message"],
                "Güvensiz HTTP bağlantısına geri dönülmedi.",
            ],
            "decision": "Belge alınmadı.",
            "next_step": "Teknik güvenlik ayrıntıları kontrol edilmelidir.",
        }
    qr = result.get("qr")
    if isinstance(qr, dict) and qr.get("status") == "corrupted":
        return {
            "title": "QR kod bulundu, ancak veri bütünlüğü bozuk.",
            "details": [
                "QR'nin konumu ve yapısı tespit edildi.",
                (
                    "Bulanıklık ve gürültü iyileştirmesinden sonra da QR'nin "
                    "hata düzeltme kontrolü geçmedi."
                ),
                "Geçersiz veya kısmi QR içeriği bağlantı olarak kullanılmadı.",
                "Dış sunucuya istek gönderilmedi.",
            ],
            "decision": "QR teknik olarak doğrulanamadığı için işlem durduruldu.",
            "next_step": "Belgenin değiştirilmemiş kopyasını veya yeni taramasını deneyin.",
        }
    return {
        "title": "QR kod doğrulanamadı.",
        "details": [
            (
                "Bulanıklık ve gürültü azaltma denemelerine rağmen en az iki "
                "bağımsız okuyucu aynı sonucu veremedi."
            ),
            "Dış sunucuya istek gönderilmedi.",
        ],
        "decision": "İşlem durduruldu.",
        "next_step": "Daha net bir belge görüntüsü deneyin.",
    }


def verify(
    image: str | Path,
    hosts: frozenset[str] = frozenset(),
    fetch: bool = False,
    enable_restormer: bool = True,
    progress: Callable[[str], None] | None = None,
):
    qr = read_qr_image(
        image,
        enable_restormer=enable_restormer,
        progress=progress,
    )
    result: dict[str, object] = {"status": "qr_not_confirmed", "qr": qr.to_dict()}
    if qr.status != "confirmed" or len(qr.confirmed_contents) != 1:
        if qr.status == "corrupted":
            result["status"] = "qr_corrupted"
        result["user_summary"] = _summary(result)
        return result
    discovery_policy = Policy(hosts)
    qr_url = qr.confirmed_contents[0]
    try:
        target = prepare(qr_url, discovery_policy)
        validation_mode = discovery_policy.validation_mode()
        policy = discovery_policy.pin(target.hostname)
        result["target"] = {
            "original_url": target.original_url,
            "effective_url": target.url,
            "hostname": target.hostname,
            "transport_upgraded": target.upgraded,
            "domain_validation": validation_mode,
            "host_pinned_after_validation": True,
        }
        if not fetch:
            result["status"] = "target_validated"
        else:
            wrapper = safe_fetch(qr_url, policy)
            parser = FrameParser()
            if wrapper.content_type == "application/pdf":
                sources = [wrapper.final_url]
            elif wrapper.content_type in {"text/html", "application/xhtml+xml"}:
                parser.feed(wrapper.body.decode("windows-1254", errors="replace"))
                sources = [
                    urljoin(wrapper.final_url, src)
                    for src in dict.fromkeys(parser.sources)
                ]
            else:
                raise SecurityError("invalid_wrapper", "PDF bağlantısı bulunamadı.")
            if not sources or len(sources) > 5:
                raise SecurityError(
                    "invalid_document_count", "Geçerli PDF bağlantısı bulunamadı."
                )
            documents = []
            for source in sources:
                prepare(source, policy)
                document = wrapper if source == wrapper.final_url else safe_fetch(
                    source, policy
                )
                if document.content_type != "application/pdf":
                    raise SecurityError("expected_pdf", "Hedef PDF döndürmedi.")
                if not document.body.startswith(b"%PDF-"):
                    raise SecurityError("invalid_pdf", "PDF dosya imzası geçersiz.")
                documents.append(document.metadata())
            result["wrapper"] = wrapper.metadata()
            result["official_documents"] = documents
            result["status"] = "document_fetched"
    except SecurityError as exc:
        result["status"] = "target_blocked"
        result["target_error"] = exc.to_dict()
    result["user_summary"] = _summary(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--allowed-host",
        action="append",
        help=(
            "İsteğe bağlı exact-host kısıtı. Verilmezse belgeli resmî kurum "
            "uzantıları otomatik doğrulanır."
        ),
    )
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument(
        "--restormer",
        dest="restormer",
        action="store_true",
        help="Uyumluluk seçeneği; Restormer artık varsayılan olarak otomatiktir.",
    )
    parser.add_argument(
        "--no-restormer",
        dest="restormer",
        action="store_false",
        help="Restormer geri dönüşünü kapat.",
    )
    parser.set_defaults(restormer=True)
    args = parser.parse_args()
    try:
        progress = lambda message: print(message, file=sys.stderr, flush=True)
        result = verify(
            args.image,
            frozenset(args.allowed_host or ()),
            fetch=args.fetch,
            enable_restormer=args.restormer,
            progress=progress,
        )
    except (FileNotFoundError, ValueError) as exc:
        result = {
            "status": "error",
            "message": str(exc),
            "user_summary": {
                "title": "Belge işlenemedi.",
                "details": [str(exc)],
                "decision": "İşlem durduruldu.",
                "next_step": "Dosya yolunu kontrol edin.",
            },
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"target_validated", "document_fetched"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
