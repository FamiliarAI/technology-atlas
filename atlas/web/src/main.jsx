import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import '@fontsource/jura/latin-300.css';
import '@fontsource/jura/latin-400.css';
import '@fontsource/jura/latin-600.css';
import '@fontsource/newsreader/latin-400.css';
import '@fontsource/newsreader/latin-400-italic.css';
import '@fontsource/newsreader/latin-500.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/dm-sans/latin-400.css';
import '@fontsource/dm-sans/latin-500.css';
import './styles.css';
import './paper.css';
import './paper-site.css';
import App from './App.jsx';
import { applyStyle } from './style.js';

// Before the first paint, so a paper page never flashes dark.
applyStyle();

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
