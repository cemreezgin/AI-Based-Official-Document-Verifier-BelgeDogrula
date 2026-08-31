import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BelgeDoğrula | Yerel Belge Kontrolü",
  description: "QR, PaddleOCR, genel benzerlik ve yerel Qwen destekli metin karşılaştırma sistemi.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
