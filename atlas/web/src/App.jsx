import { lazy, Suspense } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import Layout from './Layout.jsx';
import { AtlasProvider } from './data.jsx';
import Home from './pages/Home.jsx';
import Atlas from './pages/Atlas.jsx';
import Breakthrough from './pages/Breakthrough.jsx';
import Field from './pages/Field.jsx';
import About from './pages/About.jsx';
import NotFound from './pages/NotFound.jsx';

// Share cards (/share/...) are images for link previews: drawn alone, outside the layout, and
// loaded only when asked for (python3 -m atlas.share screenshots them).
const Share = lazy(() => import('./Share.jsx'));

// Each page sets its own document.title (pages/common.jsx useTitle; Atlas.jsx sets its own).
export default function App() {
  const location = useLocation();
  if (location.pathname.startsWith('/share/')) {
    return (
      <AtlasProvider>
        <Suspense fallback={null}>
          <Share />
        </Suspense>
      </AtlasProvider>
    );
  }
  return (
    <MotionConfig reducedMotion="user">
      <AtlasProvider>
        <Layout>
          <Routes location={location}>
            <Route path="/" element={<Home />} />
            <Route path="/atlas" element={<Atlas />} />
            <Route path="/b/:id" element={<Breakthrough />} />
            <Route path="/draft/:id" element={<Breakthrough draft />} />
            <Route path="/hand/:id" element={<Breakthrough draft hand />} />
            <Route path="/field/:field" element={<Field />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </AtlasProvider>
    </MotionConfig>
  );
}
