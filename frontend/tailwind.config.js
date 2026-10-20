/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "#4ade80",
        ink: { 950: "#0a0d0b", 900: "#101513", 800: "#171e1a", 700: "#222b26", 600: "#2f3a33", 400: "#6b7a71", 300: "#97a69c", 200: "#c6d1ca" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
  plugins: [],
};
