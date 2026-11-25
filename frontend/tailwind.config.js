/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // "short" is a screen under 840px tall (a 768p laptop): the glance view drops its secondary rows so nothing clips.
      screens: { short: { raw: "(max-height: 840px)" } },
      colors: {
        accent: "#4ade80",
        ink: { 950: "#0a0d0b", 900: "#101513", 800: "#171e1a", 700: "#222b26", 600: "#2f3a33", 500: "#4d5a52", 400: "#6b7a71", 300: "#97a69c", 200: "#c6d1ca" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
  plugins: [],
};
