import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
 root:'frontend',base:process.env.PAGES_BASE||'/multi-ai-portal/',plugins:[react()],
 define:{'process.env.NEXT_PUBLIC_PORTAL_BACKEND_URL':JSON.stringify(process.env.PORTAL_BACKEND_URL||'')},
 build:{outDir:'../dist/pages',emptyOutDir:true},
});
