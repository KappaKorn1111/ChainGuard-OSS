# ChainGuard OSS frontend

React, TypeScript, Vite, and Tailwind UI for submitting and inspecting ChainGuard jobs.

```bash
npm ci
VITE_API_URL=http://localhost:8000 npm run dev
```

The development server listens on <http://localhost:3000>. Production builds embed
`VITE_API_URL` at build time:

```bash
VITE_API_URL=https://api.example.com npm run build
```

Use the repository-level Compose stack for normal end-to-end development.
