import type { Metadata } from "next";
import { Roboto } from "next/font/google";
import "./globals.css";
import ThemeRegistry from "./ThemeRegistry";

const roboto = Roboto({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "PDF Redactor",
  description: "Redact multi-show sponsorship contracts by show",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={roboto.className}>
      <body className="antialiased">
        <ThemeRegistry>{children}</ThemeRegistry>
      </body>
    </html>
  );
}
