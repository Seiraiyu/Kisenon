import type { ReactNode } from "react";

export const metadata = { title: "Kisenon + AI SDK" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", maxWidth: 760, margin: "2rem auto", padding: "0 1rem" }}>
        {children}
      </body>
    </html>
  );
}
