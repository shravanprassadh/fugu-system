import "./globals.css";

export const metadata = {
  title: "Fugu Kernel Studio",
  description: "Deterministic multi-provider pipeline workspace",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
