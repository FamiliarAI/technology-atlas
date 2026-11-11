import { useEffect } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import Layout from './Layout.jsx';
import { AtlasProvider } from './data.jsx';
import Home from './pages/Home.jsx';
import Atlas from './pages/Atlas.jsx';
import Breakthrough from './pages/Breakthrough.jsx';
import Coming from './pages/Coming.jsx';

function Titled({ title, children }) {
  useEffect(() => {
    document.title = title;
  }, [title]);
  return children;
}

export default function App() {
  const location = useLocation();
  return (
    <MotionConfig reducedMotion="user">
      <AtlasProvider>
        <Layout>
          <Routes location={location}>
            <Route
              path="/"
              element={
                <Titled title="Technology Atlas · The wonders of the AI takeoff, named in advance">
                  <Home />
                </Titled>
              }
            />
            <Route path="/atlas" element={<Atlas />} />
            <Route path="/b/:id" element={<Breakthrough />} />
            <Route path="/field/:field" element={<Coming />} />
            <Route path="/claims" element={<Coming page="claims" />} />
            <Route path="/about" element={<Coming page="about" />} />
            <Route path="*" element={<Coming page="missing" />} />
          </Routes>
        </Layout>
      </AtlasProvider>
    </MotionConfig>
  );
}
