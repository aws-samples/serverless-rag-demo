import { BrowserRouter, Routes, Route, Navigate, HashRouter } from 'react-router-dom';
import { USE_BROWSER_ROUTER } from "./common/constants";
import GlobalHeader from "./components/global-header";
import NotFound from "./pages/not-found";
import ChatPage from "./pages/chat-page";
import "./styles/app.scss";
import ConfirmUserPage from './confirmUserPage';
import axios from 'axios';


import LoginPage from './loginPage';
import UploadPage from './pages/upload-page';
import { StorageHelper } from './common/helpers/storage-helper';


export default function App() {
  const Router = USE_BROWSER_ROUTER ? BrowserRouter : HashRouter;
  // Add a request interceptor
  axios.interceptors.request.use(function (config) {
    config.headers.Authorization = StorageHelper.getAuthToken();
    return config;
  });
  const isAuthenticated = () => {
    const accessToken = sessionStorage.getItem('accessToken');
    return !!accessToken;
  };

  return (
    <div style={{ height: "100%" }}>
      <Router>
        <GlobalHeader />
        <div style={{ height: "56px", backgroundColor: "#000716" }}>&nbsp;</div>
        <div>
          <Routes>
            <Route path="/" element={isAuthenticated() ? <Navigate replace to="/chat" /> : <Navigate replace to="/login" />} />
            <Route path="/confirm" element={<ConfirmUserPage />} />
            <Route path="/chat" element={isAuthenticated() ? <ChatPage /> : <Navigate replace to="/login" />} />
            <Route path="/upload" element={isAuthenticated() ? <UploadPage /> : <Navigate replace to="/login" />} />
            <Route index path="/login" element={<LoginPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </Router>
    </div>
  );
}
