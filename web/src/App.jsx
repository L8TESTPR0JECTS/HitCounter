import { Menubar } from "primereact/menubar";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import Chat from "./pages/Chat.jsx";
import Counter from "./pages/Counter.jsx";

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      label: "Counter",
      icon: "pi pi-chart-bar",
      command: () => navigate("/")
    },
    {
      label: "Chat",
      icon: "pi pi-comments",
      command: () => navigate("/chat")
    }
  ];

  const isChat = location.pathname.startsWith("/chat");

  return (
    <div className="app">
      <Menubar model={menuItems} className={isChat ? "menu-chat" : "menu-counter"} />

      <main className="page">
        <Routes>
          <Route path="/" element={<Counter />} />
          <Route path="/chat" element={<Chat />} />
        </Routes>
      </main>
    </div>
  );
}
