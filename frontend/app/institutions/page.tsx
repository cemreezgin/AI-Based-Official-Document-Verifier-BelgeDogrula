"use client";

import Link from "next/link";
import { useState } from "react";

type Locale = "tr" | "en";

const content = {
  tr: {
    subtitle: "Resmî belge doğrulama sistemi",
    home: "Ana sayfa",
    institutions: "Kurumlar için",
    kicker: "KURUMSAL ÇÖZÜMLER",
    title: "Belge doğrulamayı kurumunuzun güvenli iş akışına taşıyın.",
    intro: "BelgeDoğrula; QR doğrulama, OCR ve metin karşılaştırmasını yerel, denetlenebilir ve kurum ihtiyaçlarına uyarlanabilir tek bir akışta birleştirir.",
    points: [
      ["Yerel çalışma", "Belge işleme kurum altyapısında veya kontrollü yerel ortamda yürütülebilir."],
      ["Güvenli entegrasyon", "Mevcut uygulama ve iş akışlarına API katmanı üzerinden bağlanabilir."],
      ["Denetlenebilir sonuç", "Doğrulama kararı, güvenlik kontrolleri ve karşılaştırma özetiyle açıklanır."],
    ],
    footer: "BelgeDoğrula · Kurumsal belge doğrulama",
  },
  en: {
    subtitle: "Official document verification system",
    home: "Home",
    institutions: "For institutions",
    kicker: "ENTERPRISE SOLUTIONS",
    title: "Bring document verification into your organization’s secure workflow.",
    intro: "BelgeDoğrula combines QR validation, OCR and text comparison in a local, auditable workflow that can be adapted to institutional requirements.",
    points: [
      ["Local operation", "Document processing can run within institutional infrastructure or a controlled local environment."],
      ["Secure integration", "It can connect to existing applications and workflows through an API layer."],
      ["Auditable results", "Each decision is explained with security checks and a comparison summary."],
    ],
    footer: "BelgeDoğrula · Enterprise document verification",
  },
} as const;

export default function InstitutionsPage() {
  const [locale, setLocale] = useState<Locale>("tr");
  const text = content[locale];

  return (
    <main className="institutions-page">
      <header className="site-header">
        <Link className="brand" href="/" aria-label={text.home}>
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
          <span className="brand-copy">
            <strong>Belge<span>Doğrula</span></strong>
            <small>{text.subtitle}</small>
          </span>
        </Link>
        <div className="header-right">
          <Link href="/">{text.home}</Link>
          <span className="active-nav">{text.institutions}</span>
          <label className="language-select">
            <span className="sr-only">Language / Dil</span>
            <select value={locale} onChange={(event) => setLocale(event.target.value as Locale)} aria-label="Language / Dil">
              <option value="tr">TR</option>
              <option value="en">EN</option>
            </select>
          </label>
        </div>
      </header>

      <section className="institutions-hero">
        <div className="institutions-hero-copy">
          <p className="eyebrow"><span /> {text.kicker}</p>
          <h1>{text.title}</h1>
          <p className="institutions-intro">{text.intro}</p>
        </div>

        <div className="institutions-brand-panel" aria-label="BelgeDoğrula">
          <span className="brand-mark institution-logo" aria-hidden="true"><i /><i /><i /><i /></span>
          <span className="brand-copy">
            <strong>Belge<span>Doğrula</span></strong>
            <small>{text.subtitle}</small>
          </span>
        </div>
      </section>

      <section className="institutions-features" aria-label={text.institutions}>
        {text.points.map(([title, description], index) => (
          <article key={title}>
            <span>0{index + 1}</span>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>

      <footer className="institutions-footer">
        <span>{text.footer}</span>
        <Link href="/">← {text.home}</Link>
      </footer>
    </main>
  );
}
