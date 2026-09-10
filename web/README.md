# Hit Counter Web

Frontend for the Hit Counter project, built with React + Vite and served via Nginx in production. The UI uses PrimeReact and React Router.

## Requirements
- Node.js 18+
- npm

## Local Development
```bash
npm install
npm run dev
```
The dev server binds to `0.0.0.0:3000`.

## Build
```bash
npm run build
```
Build output is written to `dist/`.

## Preview Production Build
```bash
npm run preview
```
The preview server binds to `0.0.0.0:3000`.

## Docker
```bash
docker build -t hit-counter-web .
docker run --rm -p 8080:80 hit-counter-web
```
Nginx serves the SPA with a fallback to `index.html` for client-side routing.

## Scripts
- `dev`: Start the Vite dev server on port 3000
- `build`: Create a production build
- `preview`: Preview the production build locally
