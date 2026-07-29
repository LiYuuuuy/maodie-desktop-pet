import React from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { PetApp } from "./app/PetApp";
import { ChatApp } from "./app/ChatApp";
import { SettingsApp } from "./app/SettingsApp";
import "./styles.css";

const windowLabel = (() => {
  try {
    return getCurrentWindow().label;
  } catch {
    return new URLSearchParams(window.location.search).get("window") ?? "pet";
  }
})();

const App = windowLabel === "chat" ? ChatApp : windowLabel === "settings" ? SettingsApp : PetApp;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
