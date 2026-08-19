/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f3efe6",
        ink: "#1c1917",
        rule: "#d6d0c4",
        forest: "#1f4b3a",
        moss: "#2f6b45",
        rust: "#8a2f2f",
        amber: "#8a5a12",
      },
      fontFamily: {
        serif: ['"Iowan Old Style"', "Palatino Linotype", "Palatino", "Georgia", "serif"],
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
