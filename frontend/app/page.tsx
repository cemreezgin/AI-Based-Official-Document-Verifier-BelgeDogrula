"use client";

import Link from "next/link";
import { DragEvent, useEffect, useRef, useState } from "react";

type Stage = "idle" | "processing" | "complete" | "error";
type Locale = "tr" | "en";
type Policy = "privacy" | "kvkk" | "accessibility";

const copy = {
  tr: {
    subtitle: "Resmî belge doğrulama sistemi", help: "Yardım", institutions: "Kurumlar için",
    hero: "Resmî belgeleri", heroEm: "güvenle doğrulayın.", decoder: "Decoder uzlaşması", localOcr: "Yerel Türkçe OCR", noStorage: "Dosyalar saklanmaz",
    upload: "Belgenizi yükleyin", maxSize: "En fazla 15 MB", drop: "Dosyayı buraya sürükleyin", localOnly: "Belge yalnızca yerel doğrulama servisine gönderilir", choose: "Dosya seç",
    processing: "İşleniyor", complete: "Analiz tamamlandı", failed: "İşlem başarısız", privacy: "Gizlilik:", privacyText: "Dosya geçici dizinde işlenir ve istek tamamlandığında otomatik olarak silinir.", verify: "Doğrulamayı başlat",
    examining: "Belge inceleniyor", fewSeconds: "Birkaç saniye kaldı", estimated: "Tahmini", seconds: "sn kaldı", minutes: "dk",
    result: "DOĞRULAMA SONUCU", sufficient: "Metinlerin genel benzerliği yeterli", insufficient: "Metinlerin genel benzerliği yetersiz", qrFailed: "QR kod güvenle doğrulanamadı", blocked: "Resmî hedef güvenlik kontrolünü geçemedi", incomplete: "Metin karşılaştırması tamamlanamadı",
    grayDecision: "Genel benzerlik gri bölgede kaldı; Qwen3:4b kararı", autoMatch: "Türkçe karakter ve biçim farkları normalize edildikten sonra otomatik eşleşme eşiği sağlandı.", noOfficial: "Karşılaştırma için resmî belge metni alınamadı.", belowThreshold: "Genel metin benzerliği Qwen inceleme eşiğinin altında kaldı.", similarity: "Genel metin benzerliği",
    sourceReceived: "Resmî kaynak alındı", sourceMissing: "Resmî kaynak tamamlanmadı", noSource: "Kaynak bilgisi yok", ocrLines: "OCR satırı",
    showTechnical: "Teknik detayları göster", hideTechnical: "Teknik detayları kapat", technicalSubtitle: "OCR metinleri ve karar yöntemi", pairedOcr: "Karşılıklı OCR metni", qwenZone: "Qwen bölgesi", finalDecision: "Final karar", matched: "EŞLEŞTİ", notMatched: "EŞLEŞMEDİ", highMatch: "Yüksek genel benzerlik ile otomatik eşleşti", lowReject: "Düşük genel benzerlik ile otomatik reddedildi", uploadedDoc: "Yüklenen belge", officialDoc: "QR ile açılan resmî belge",
    print: "Raporu yazdır", newVerification: "Yeni belge doğrula", serviceError: "SERVİS HATASI", cannotProcess: "Belge işlenemedi", noResult: "Sonuç yok", chooseNew: "Yeni belge seç",
    localAuditable: "Yerel ve denetlenebilir", helpTitle: "Belge doğrulama süreci üç adımda ilerler.", qrVerified: "QR doğrulanır", qrVerifiedText: "QR içeriği, iki ayrı doğrulama kaynağıyla kontrol edilir.", textsExtracted: "Metinler çıkarılır", textsExtractedText: "Belgelerin metinleri, metin tanıma teknolojisiyle ayrı ayrı okunur.", grayQwen: "Şüpheli durumlar incelenir", grayQwenText: "Sonuç net değilse, yerel bir yapay zeka modeli OCR hatası ile gerçek içerik farkını ayırmaya yardımcı olur.",
    institutionsTitle: "Kurumsal belge doğrulama için güvenli bir altyapı", institutionsText: "BelgeDoğrula, kurum içi operasyonlarda belge doğrulama süreçlerini hızlandıran, yerel çalışan ve denetlenebilir bir çözüm sunar. QR doğrulama, OCR ve metin karşılaştırmasını tek bir akışta birleştirerek hem risk yönetimini hem de denetim hazırlığını destekler.", institutionsCta: "Kurumsal demo talep edin", institutionsList: ["Yerel ve güvenli çalışma modeli", "Denetlenebilir doğrulama akışı", "Kurumsal entegrasyon ve raporlama desteği"],
  },
  en: {
    subtitle: "Official document verification system", help: "Help", institutions: "For institutions",
    hero: "Verify official documents", heroEm: "with confidence.", decoder: "Decoder consensus", localOcr: "Local OCR", noStorage: "Files are not stored",
    upload: "Upload your document", maxSize: "Up to 15 MB", drop: "Drag your file here", localOnly: "The document is sent only to the local verification service", choose: "Choose file",
    processing: "Processing", complete: "Analysis complete", failed: "Processing failed", privacy: "Privacy:", privacyText: "The file is processed in a temporary directory and deleted automatically when the request ends.", verify: "Start verification",
    examining: "Document is being examined", fewSeconds: "A few seconds remaining", estimated: "Approx.", seconds: "sec remaining", minutes: "min",
    result: "VERIFICATION RESULT", sufficient: "Overall text similarity is sufficient", insufficient: "Overall text similarity is insufficient", qrFailed: "The QR code could not be verified securely", blocked: "The official target failed security checks", incomplete: "Text comparison could not be completed",
    grayDecision: "Similarity is in the review zone; Qwen3:4b decision", autoMatch: "The automatic match threshold was met after normalizing character and formatting differences.", noOfficial: "Official document text could not be obtained for comparison.", belowThreshold: "Overall text similarity remained below the Qwen review threshold.", similarity: "Overall text similarity",
    sourceReceived: "Official source received", sourceMissing: "Official source incomplete", noSource: "Source unavailable", ocrLines: "OCR lines",
    showTechnical: "Show technical details", hideTechnical: "Hide technical details", technicalSubtitle: "OCR texts and decision method", pairedOcr: "Side-by-side OCR text", qwenZone: "Qwen zone", finalDecision: "Final decision", matched: "MATCHED", notMatched: "NOT MATCHED", highMatch: "Automatically matched with high overall similarity", lowReject: "Automatically rejected due to low overall similarity", uploadedDoc: "Uploaded document", officialDoc: "Official document opened from QR",
    print: "Print report", newVerification: "Verify another document", serviceError: "SERVICE ERROR", cannotProcess: "Document could not be processed", noResult: "No result", chooseNew: "Choose another document",
    localAuditable: "Local and auditable", helpTitle: "The document verification process runs in three steps.", qrVerified: "QR is verified", qrVerifiedText: "QR content is checked through two independent validation sources.", textsExtracted: "Texts are extracted", textsExtractedText: "The document text is read separately using text recognition technology.", grayQwen: "Unclear cases are reviewed", grayQwenText: "When the result is not clear, a local AI model helps distinguish OCR errors from meaningful content differences.",
    institutionsTitle: "A secure foundation for enterprise document verification", institutionsText: "BelgeDoğrula helps organizations streamline document verification, reduce fraud exposure and strengthen audit readiness. It combines QR validation, OCR and text comparison in a local, reviewable workflow that fits enterprise compliance processes.", institutionsCta: "Request an enterprise demo", institutionsList: ["Local and secure operating model", "Auditable verification workflow", "Enterprise integration and reporting support"],
  },
} as const;

type ProgressSnapshot = {
  status: "processing" | "completed" | "failed";
  phase: string;
  percent: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number;
};

type QwenJudgment = {
  verdict: "same" | "different" | "uncertain";
  confidence: number;
  reason_code: "exact_text" | "layout_or_order_only" | "minor_ocr_noise_only" | "substantive_text_difference" | "insufficient_evidence";
  uploaded_excerpt: string | null;
  official_excerpt: string | null;
  safety_veto: "paired_content_conflict" | null;
};

type VerificationResult = {
  status: string;
  matched?: boolean;
  matched_document_url?: string | null;
  source_page_url?: string | null;
  match_confidence?: number;
  search_stopped_early?: boolean;
  search_stop_reason?: string | null;
  qr?: {
    report?: {
      status?: string;
      confirmed_contents?: string[];
      image_quality?: Record<string, string | number>;
    };
  };
  uploaded?: {
    line_count?: number;
  };
  official?: {
    source?: { hostname?: string };
    line_count?: number;
  } | null;
  comparison?: {
    mode: "direct_text";
    decision: "match" | "mismatch";
    matched: boolean;
    exact_match: boolean;
    confidence: number;
    match_confidence: number;
    compared_token_count: number;
    matching_token_count: number;
    difference_count: number;
    match_threshold: number;
    ordered_similarity: number;
    bag_similarity: number;
    normalization: string;
    review_min_similarity?: number;
    auto_match_similarity?: number;
    decision_source: "similarity_auto_match" | "similarity_auto_reject" | "qwen_gray_zone";
    qwen_judgment: QwenJudgment | null;
    uploaded_line_count: number;
    official_line_count: number;
    uploaded_text: string;
    official_text: string;
  } | null;
  official_error?: { message?: string };
};

const progressLabels: Record<Locale, Record<string, string>> = {
  tr: { upload_validation: "Dosya güvenliği kontrol ediliyor", qr_analysis: "QR kod analiz ediliyor", uploaded_ocr: "Yüklenen belgenin metni çıkarılıyor", official_search: "Resmî belge aranıyor", official_document: "Resmî belge hazırlanıyor", official_ocr: "Resmî belgenin metni çıkarılıyor", qwen_judgment: "Qwen3:4b gri bölgeyi yorumluyor", finalizing: "Sonuç hazırlanıyor", completed: "İşlem tamamlandı", failed: "İşlem tamamlanamadı" },
  en: { upload_validation: "Checking file security", qr_analysis: "Analyzing QR code", uploaded_ocr: "Extracting uploaded document text", official_search: "Searching for the official document", official_document: "Preparing official document", official_ocr: "Extracting official document text", qwen_judgment: "Qwen3:4b is reviewing the uncertain result", finalizing: "Preparing result", completed: "Processing complete", failed: "Processing could not be completed" },
};

const qwenReasonLabels: Record<Locale, Record<QwenJudgment["reason_code"], string>> = {
  tr: { exact_text: "Metinler aynı", layout_or_order_only: "Fark yalnız yerleşim veya metin sırasından kaynaklanıyor", minor_ocr_noise_only: "Fark yalnız küçük OCR okuma gürültüsünden kaynaklanıyor", substantive_text_difference: "Belge içeriğini değiştiren metin çelişkisi var", insufficient_evidence: "Aynı belge kararı için kanıt yetersiz" },
  en: { exact_text: "Texts are identical", layout_or_order_only: "The difference is limited to layout or text order", minor_ocr_noise_only: "The difference is limited to minor OCR noise", substantive_text_difference: "There is a contradiction that changes document content", insufficient_evidence: "Evidence is insufficient to confirm the same document" },
};

function formatRemaining(seconds: number, locale: Locale) {
  const text = copy[locale];
  if (seconds <= 5) return text.fewSeconds;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes === 0) return `${text.estimated} ${remainder} ${text.seconds}`;
  if (remainder === 0) return `${text.estimated} ${minutes} ${text.minutes}`;
  return `${text.estimated} ${minutes} ${text.minutes} ${remainder} ${text.seconds}`;
}

function TextPanel({ text, label }: { text: string; label: string }) {
  return <pre className="document-text"><span className="mobile-document-label">{label}</span>{text}</pre>;
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [progress, setProgress] = useState<ProgressSnapshot>({
    status: "processing",
    phase: "upload_validation",
    percent: 1,
    elapsed_seconds: 0,
    estimated_remaining_seconds: 180,
  });
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [error, setError] = useState("");
  const [locale, setLocale] = useState<Locale>("tr");
  const [policy, setPolicy] = useState<Policy | null>(null);
  const text = copy[locale];

  useEffect(() => {
    if (!policy) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPolicy(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [policy]);

  function chooseFile(nextFile?: File) {
    if (!nextFile) return;
    setFile(nextFile);
    setStage("idle");
    setResult(null);
    setError("");
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files[0]);
  }

  async function startVerification() {
    if (!file || stage === "processing") return;
    const requestId = crypto.randomUUID();
    setStage("processing");
    setProgress({
      status: "processing",
      phase: "upload_validation",
      percent: 1,
      elapsed_seconds: 0,
      estimated_remaining_seconds: 180,
    });
    setError("");
    const pollProgress = async () => {
      try {
        const response = await fetch(`/api/v1/progress/${requestId}`, {
          cache: "no-store",
        });
        if (response.ok) {
          setProgress(await response.json() as ProgressSnapshot);
        }
      } catch {
        // The verification request remains authoritative if polling is delayed.
      }
    };
    const progressTimer = window.setInterval(pollProgress, 1000);
    try {
      const response = await fetch("/api/v1/verify", {
        method: "POST",
        body: file,
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
          "X-Request-ID": requestId,
        },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Servis HTTP ${response.status} döndürdü.`);
      }
      setResult(payload as VerificationResult);
      setProgress((current) => ({
        ...current,
        status: "completed",
        phase: "completed",
        percent: 100,
        estimated_remaining_seconds: 0,
      }));
      await new Promise((resolve) => window.setTimeout(resolve, 250));
      setStage("complete");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Belge doğrulanamadı.");
      setStage("error");
    } finally {
      window.clearInterval(progressTimer);
    }
  }

  function reset() {
    setFile(null);
    setStage("idle");
    setResult(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  }

  const decision = result?.comparison?.decision;
  const isMatched = result?.matched === true || result?.status === "MATCHED";
  const decisionTitle = isMatched
    ? text.sufficient
    : decision === "mismatch"
      ? text.insufficient
      : result?.status === "qr_not_confirmed"
        ? text.qrFailed
        : result?.status === "BLOCKED" || result?.status === "official_target_blocked"
          ? text.blocked
          : text.incomplete;
  const decisionDescription = isMatched
    ? result?.comparison?.decision_source === "qwen_gray_zone"
      ? `${text.grayDecision}: ${qwenReasonLabels[locale][result.comparison.qwen_judgment!.reason_code]}.`
      : text.autoMatch
    : result?.official_error?.message
      || (result?.comparison
        ? result.comparison.decision_source === "qwen_gray_zone"
          ? `${text.grayDecision}: ${qwenReasonLabels[locale][result.comparison.qwen_judgment!.reason_code]}.`
          : text.belowThreshold
        : text.noOfficial);
  const confidence = Math.round((result?.match_confidence ?? result?.comparison?.confidence ?? 0) * 100);

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="BelgeDoğrula ana sayfa">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <span className="brand-copy"><strong>Belge<span>Doğrula</span></strong></span>
        </a>
        <div className="header-right">
          <a href="#help">{text.help}</a>
          <Link href="/institutions">{text.institutions}</Link>
          <label className="language-select">
            <span className="sr-only">Language / Dil</span>
            <select value={locale} onChange={(event) => setLocale(event.target.value as Locale)} aria-label="Language / Dil">
              <option value="tr">TR</option>
              <option value="en">EN</option>
            </select>
          </label>
        </div>
      </header>

      <section className="hero" id="top">
        <h1>{text.hero}<br /><em>{text.heroEm}</em></h1>
        <div className="trust-row" aria-label="Güvenlik özellikleri">
          <span><b>✓</b> {text.decoder}</span>
          <span><b>✓</b> {text.localOcr}</span>
          <span><b>✓</b> {text.noStorage}</span>
        </div>
      </section>

      <section className="workspace" aria-label="Belge doğrulama alanı">
        <div className="workspace-head">
          <div><h2>{text.upload}</h2></div>
          <span className="formats">PDF · JPG · PNG <b>{text.maxSize}</b></span>
        </div>

        {!file ? (
          <div
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <input
              ref={inputRef}
              id="document-upload"
              type="file"
              accept=".pdf,image/jpeg,image/png"
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
            <div className="upload-symbol" aria-hidden="true"><span>↑</span></div>
            <h3>{text.drop}</h3>
            <button className="primary-btn" type="button" onClick={() => inputRef.current?.click()}>{text.choose}</button>
          </div>
        ) : (
          <div className="selected-file">
            <div className="file-icon" aria-hidden="true">DOC</div>
            <div className="file-info">
              <strong>{file.name}</strong>
              <span>{file.type || "belge"} · {(file.size / 1024 / 1024).toFixed(1)} MB</span>
            </div>
            {stage === "idle" && <button className="remove-btn" type="button" onClick={reset} aria-label="Dosyayı kaldır">×</button>}
            {stage === "processing" && <span className="processing-pill"><i /> {text.processing}</span>}
            {stage === "complete" && <span className="success-pill">✓ {text.complete}</span>}
            {stage === "error" && <span className="warning-pill">! {text.failed}</span>}
          </div>
        )}

        {file && stage === "idle" && (
          <div className="action-row">
            <p><b>{text.privacy}</b> {text.privacyText}</p>
            <button className="verify-btn" type="button" onClick={startVerification}>{text.verify} <span>→</span></button>
          </div>
        )}

        {stage === "processing" && (
          <div className="progress-panel" aria-live="polite">
            <div className="progress-head">
              <div><h2>{text.examining}</h2></div>
              <strong className="progress-percentage">%{Math.round(progress.percent)}</strong>
            </div>
            <div
              className="progress-line"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress.percent)}
            >
              <span style={{ width: `${progress.percent}%` }} />
            </div>
            <div className="progress-meta">
              <strong>{progressLabels[locale][progress.phase] || text.processing}</strong>
              <span>{formatRemaining(progress.estimated_remaining_seconds, locale)}</span>
            </div>
          </div>
        )}
      </section>

      {stage === "complete" && result && (
        <section className="result-section">
          <div className={`result-summary ${!isMatched ? "unavailable-summary" : ""}`}>
            <div className={`result-badge ${!isMatched ? "unavailable-badge" : ""}`}><span>{isMatched ? "✓" : "!"}</span></div>
            <div>
              <span className="result-kicker">{text.result} · {result.status}</span>
              <h2>{decisionTitle}</h2>
              <p>{decisionDescription}</p>
            </div>
            <div className={`score ${!isMatched ? "unavailable-score" : ""}`}><strong>{result.comparison ? `%${confidence}` : "—"}</strong><span>{text.similarity}</span></div>
          </div>
          <div className={`source-strip ${!result.official ? "unavailable-source" : ""}`}>
            <span><b>{result.official ? "✓" : "!"}</b> {result.official ? text.sourceReceived : text.sourceMissing}</span>
            <strong>{result.official?.source?.hostname || text.noSource}</strong>
            <span className="masked-url">{text.ocrLines}: {result.uploaded?.line_count ?? 0} / {result.official?.line_count ?? 0}</span>
          </div>
          {result.comparison && (
            <details className="technical-details">
              <summary>
                <span>
                  <strong><span className="when-closed">{text.showTechnical}</span><span className="when-open">{text.hideTechnical}</span></strong>
                  <small>{text.technicalSubtitle}</small>
                </span>
                <i aria-hidden="true" />
              </summary>
              <div className="comparison-card">
                <div className="table-title">
                  <h3>{text.pairedOcr}</h3>
                  <span>%{Math.round(result.comparison.match_confidence * 100)} {text.similarity.toLocaleLowerCase(locale)} · {text.qwenZone} %{Math.round((result.comparison.review_min_similarity ?? 0.75) * 100)}–%{Math.round((result.comparison.auto_match_similarity ?? 0.85) * 100)}</span>
                </div>
                <div className={`threshold-verdict ${result.comparison.matched ? "threshold-match" : "threshold-mismatch"}`}>
                  <strong>{text.finalDecision}: {result.comparison.matched ? text.matched : text.notMatched}</strong>
                  <span>{result.comparison.decision_source === "qwen_gray_zone" ? `Qwen3:4b: ${qwenReasonLabels[locale][result.comparison.qwen_judgment!.reason_code]}` : result.comparison.decision_source === "similarity_auto_match" ? text.highMatch : text.lowReject}</span>
                </div>
                <div className="text-comparison-head" aria-hidden="true">
                  <strong>{text.uploadedDoc}</strong>
                  <strong>{text.officialDoc}</strong>
                </div>
                <div className="text-comparison-grid" aria-label="Karşılıklı belge metni">
                  <TextPanel text={result.comparison.uploaded_text} label={text.uploadedDoc} />
                  <TextPanel text={result.comparison.official_text} label={text.officialDoc} />
                </div>
              </div>
            </details>
          )}
          <div className="result-actions">
            <button type="button" className="secondary-btn" onClick={() => window.print()}>{text.print}</button>
            <button type="button" className="verify-btn" onClick={reset}>{text.newVerification} <span>→</span></button>
          </div>
        </section>
      )}

      {stage === "error" && (
        <section className="result-section">
          <div className="result-summary unavailable-summary">
            <div className="result-badge unavailable-badge"><span>!</span></div>
            <div><span className="result-kicker">{text.serviceError}</span><h2>{text.cannotProcess}</h2><p>{error}</p></div>
            <div className="score unavailable-score"><strong>—</strong><span>{text.noResult}</span></div>
          </div>
          <div className="result-actions"><button type="button" className="verify-btn" onClick={reset}>{text.chooseNew} <span>→</span></button></div>
        </section>
      )}

      <section className="how" id="help">
        <div className="how-copy"><span className="eyebrow"><span /> {text.localAuditable}</span><h2>{text.helpTitle}</h2></div>
        <div className="how-steps">
          <article><h3>{text.qrVerified}</h3><p>{text.qrVerifiedText}</p></article>
          <article><h3>{text.textsExtracted}</h3><p>{text.textsExtractedText}</p></article>
          <article><h3>{text.grayQwen}</h3><p>{text.grayQwenText}</p></article>
        </div>
      </section>

      <footer className="legal-footer">
        <div className="footer-brand">
          <span className="brand-mark footer-brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <div>
            <span>BelgeDoğrula</span>
            <p>{text.subtitle}</p>
          </div>
        </div>
        <nav aria-label={locale === "tr" ? "Yasal ve erişilebilirlik bağlantıları" : "Legal and accessibility links"}>
          <button type="button" onClick={() => setPolicy("privacy")}>{locale === "tr" ? "Gizlilik politikası" : "Privacy policy"}</button>
          <i aria-hidden="true">·</i>
          <button type="button" onClick={() => setPolicy("kvkk")}>{locale === "tr" ? "KVKK aydınlatma metni" : "KVKK privacy notice"}</button>
          <i aria-hidden="true">·</i>
          <button type="button" onClick={() => setPolicy("accessibility")}>{locale === "tr" ? "Erişilebilirlik" : "Accessibility"}</button>
        </nav>
      </footer>

      {policy && (
        <div className="policy-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPolicy(null); }}>
          <section className="policy-dialog" role="dialog" aria-modal="true" aria-labelledby="policy-title">
            <button className="policy-close" type="button" onClick={() => setPolicy(null)} autoFocus aria-label={locale === "tr" ? "Pencereyi kapat" : "Close dialog"}>×</button>
            {policy === "kvkk" && (locale === "tr" ? (
              <>
                <span className="policy-kicker">6698 SAYILI KANUN · AYDINLATMA</span>
                <h2 id="policy-title">KVKK aydınlatma metni</h2>
                <p className="policy-warning"><strong>Önemli:</strong> Bu geliştirme sürümünde veri sorumlusunun ticari unvanı, adresi ve KVKK başvuru kanalı yapılandırılmamıştır. Bu alanlar gerçek kurum bilgileriyle tamamlanmadan metin nihai aydınlatma metni veya mevzuata uyum sertifikası olarak kullanılamaz.</p>
                <h3>İşlenen veriler ve amaç</h3>
                <p>Yüklediğiniz belge; ad, kurum, adres, belge numarası, tarih, imza görüntüsü ve QR doğrulama adresi gibi kişisel veriler içerebilir. Veriler yalnız belgenin QR kodunu çözmek, resmî kaynağı güvenli biçimde almak, iki OCR metnini karşılaştırmak ve doğrulama sonucunu üretmek amacıyla işlenir.</p>
                <h3>Toplama yöntemi, saklama ve aktarım</h3>
                <p>Belge kullanıcı tarafından elektronik ortamda yüklenir. Dosya ve indirilen resmî belge geçici dizinde işlenir ve istek tamamlandığında silinir. Belge gövdeleri uygulama loglarına yazılmaz veya kalıcı veri tabanına kaydedilmez. Yalnız içerik taşımayan işlem ilerleme kaydı bellekte en fazla bir saat tutulur. Yüklenen belge OpenAI veya ChatGPT hizmetlerine gönderilmez; OCR ve Qwen değerlendirmesi yerel servislerde yürütülür. QR adresine erişim sırasında yalnız izin verilen resmî alan adına ağ isteği yapılır.</p>
                <h3>Hukuki sebep ve veri sorumlusu</h3>
                <p>KVKK’nın 5 ve gerekiyorsa 6’ncı maddesindeki somut işleme şartı, sistemi hizmete sunan veri sorumlusu tarafından kullanım senaryosuna göre belirlenmelidir. Aydınlatma metni açık rıza yerine geçmez. Üretim yayını öncesinde veri sorumlusunun kimliği, temsilcisi, hukuki sebep, varsa alıcı grupları ve başvuru kanalı bu bölüme eklenmelidir.</p>
                <h3>İlgili kişinin hakları</h3>
                <p>KVKK’nın 11’inci maddesi kapsamında verinizin işlenip işlenmediğini öğrenme, bilgi talep etme, amacına uygun kullanımı öğrenme, aktarılan üçüncü kişileri bilme, düzeltme, silme veya yok etme isteme, yapılan işlemlerin alıcılara bildirilmesini isteme, otomatik analiz sonucuna itiraz etme ve kanuna aykırı işleme nedeniyle zararın giderilmesini talep etme haklarına sahipsiniz.</p>
                <p className="policy-source">Resmî kaynaklar: <a href="https://www.kvkk.gov.tr/Icerik/4132/aydinlatma-yukumlulugunun-yerine-getirilmesinde-uyulacak-usul-ve-esaslar-hakkinda-teblig" target="_blank" rel="noreferrer">Aydınlatma Tebliği</a> · <a href="https://www.kvkk.gov.tr/Icerik/5441/KISISEL-VERILERIN-SILINMESI-YOK-EDILMESI-VEYA-ANONIM-HALE-GETIRILMESI-HAKKINDA-YONETMELIK" target="_blank" rel="noreferrer">Silme ve İmha Yönetmeliği</a></p>
              </>
            ) : (
              <>
                <span className="policy-kicker">LAW NO. 6698 · PRIVACY NOTICE</span>
                <h2 id="policy-title">KVKK privacy notice</h2>
                <p className="policy-warning"><strong>Important:</strong> The controller’s legal name, address and data-subject request channel are not configured in this development build. Until completed with real institutional information, this text is not a final legal notice or certification of compliance.</p>
                <h3>Data and purpose</h3><p>An uploaded document may contain names, institutions, addresses, document numbers, dates, signatures and a QR verification URL. Data is processed only to decode the QR code, securely retrieve the official source, compare OCR texts and produce a verification result.</p>
                <h3>Collection, retention and transfer</h3><p>The file is uploaded electronically. Uploaded and official files are processed in temporary directories and deleted when the request ends. Document bodies are not written to application logs or a persistent database. Body-free progress metadata remains in memory for up to one hour. The document is not sent to OpenAI or ChatGPT; OCR and Qwen processing are local. Network access is limited to the allowed official QR domain.</p>
                <h3>Legal basis and controller</h3><p>The controller deploying the service must identify the concrete processing condition under Articles 5 and, where relevant, 6 of Law No. 6698. A privacy notice does not replace explicit consent. Controller identity, legal basis, recipients and request channel must be completed before production use.</p>
                <h3>Data-subject rights</h3><p>Article 11 provides rights to learn whether data is processed, request information, learn its purpose and recipients, request correction or deletion, request notification to recipients, object to solely automated outcomes and claim compensation for unlawful processing.</p>
              </>
            ))}
            {policy === "privacy" && (locale === "tr" ? (
              <><span className="policy-kicker">GİZLİLİK</span><h2 id="policy-title">Gizlilik politikası</h2><p>BelgeDoğrula, yüklenen belgeleri yalnız doğrulama işlemi süresince kullanır. Dosyalar geçici dizinde tutulur, belge içerikleri loglanmaz ve işlem sonunda silinir. Sonuç ekranındaki OCR metinleri tarayıcı belleğinde yeni işlem başlatılana veya sayfa kapatılana kadar görüntülenir.</p><p>QR hedeflerine yalnız güvenlik politikasının izin verdiği resmî alan adları üzerinden erişilir. Localhost, özel IP adresleri, file protokolü ve izin verilmeyen yönlendirmeler engellenir.</p></>
            ) : (
              <><span className="policy-kicker">PRIVACY</span><h2 id="policy-title">Privacy policy</h2><p>BelgeDoğrula uses uploaded documents only for the duration of verification. Files remain in temporary directories, document contents are not logged, and files are deleted when processing ends. OCR text remains visible in browser memory until a new operation starts or the page closes.</p><p>QR targets are accessed only through official domains allowed by the security policy. Localhost, private IP addresses, file URLs and unauthorized redirects are blocked.</p></>
            ))}
            {policy === "accessibility" && (locale === "tr" ? (
              <><span className="policy-kicker">ERİŞİLEBİLİRLİK</span><h2 id="policy-title">Erişilebilirlik bildirimi</h2><p>Arayüz klavye kullanımını, görünür odak durumlarını, anlamsal başlıkları, form etiketlerini, ilerleme çubuğu bildirimlerini ve ekran okuyucuya uygun açılır teknik detayları destekleyecek şekilde hazırlanmıştır.</p><p>Erişilebilirlikle ilgili bir engel tespit edilirse, üretim ortamında kurumun erişilebilirlik iletişim kanalı üzerinden bildirim yapılabilmelidir. Bu geliştirme sürümünde kurumsal iletişim kanalı henüz yapılandırılmamıştır.</p></>
            ) : (
              <><span className="policy-kicker">ACCESSIBILITY</span><h2 id="policy-title">Accessibility statement</h2><p>The interface supports keyboard navigation, visible focus states, semantic headings, form labels, progress announcements and screen-reader-friendly expandable technical details.</p><p>A production deployment should provide an institutional accessibility contact channel. No institutional contact is configured in this development build.</p></>
            ))}
          </section>
        </div>
      )}
    </main>
  );
}
