import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/outfit/400.css';
import '@fontsource/outfit/600.css';
import '@fontsource/dm-sans/400.css';
import '@fontsource/dm-sans/500.css';
import '@fontsource/jetbrains-mono/400.css';
import './styles.css';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(<App />);
