/** @type {import('postcss-load-config').Config} */
// Intentionally minimal — does not use tailwindcss.
// Overrides the parent frontend/postcss.config.mjs which references @tailwindcss/postcss.
const config = {
  plugins: {},
}

export default config
