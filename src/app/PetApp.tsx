import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import {
  LogicalPosition,
  LogicalSize,
  availableMonitors,
  currentMonitor,
  getAllWindows,
  getCurrentWindow,
} from "@tauri-apps/api/window";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { DropOverlay } from "../components/DropOverlay";
import { PetSprite } from "../components/PetSprite";
import { classifyGesture, type PointerSample } from "../pet/clickGesture";
import {
  deduplicatePaths,
  summarizeTrashResult,
  type TrashBatchResult,
} from "../pet/fileDropController";
import { IdleScheduler } from "../pet/idleScheduler";
import { startWalking } from "../pet/movementController";
import { INITIAL_PET_STATE, reducePet } from "../pet/petMachine";
import type { PetEvent } from "../pet/types";
import { DEFAULT_SETTINGS } from "../settings/defaults";
import {
  loadPetPosition,
  loadSettings,
  savePetPosition,
} from "../settings/settingsStore";
import type { AppSettings } from "../settings/schema";

export function PetApp() {
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [machine, rawDispatch] = useReducer(
    (state: typeof INITIAL_PET_STATE, event: PetEvent) => reducePet(state, event, settings),
    INITIAL_PET_STATE,
  );
  const [toast, setToast] = useState("");
  const [direction, setDirection] = useState<"left" | "right">("right");
  const pointerStart = useRef<PointerSample | undefined>(undefined);
  const dragStarted = useRef(false);
  const scheduler = useMemo(() => new IdleScheduler(), []);
  const appWindow = useMemo(() => getCurrentWindow(), []);
  const dispatch = useCallback((event: PetEvent) => rawDispatch(event), []);

  const scheduleIdle = useCallback(() => {
    scheduler.schedule(settings.idleScheduler, (random) => dispatch({ type: "IDLE_TIMEOUT", random }));
  }, [dispatch, scheduler, settings.idleScheduler]);

  useEffect(() => {
    void loadSettings().then(async (loaded) => {
      setSettings(loaded);
      await appWindow.setAlwaysOnTop(loaded.pet.alwaysOnTop);
      await appWindow.setSize(new LogicalSize(256 * loaded.pet.scale, 256 * loaded.pet.scale));
      if (loaded.pet.savePosition) {
        const position = await loadPetPosition();
        if (position) {
          const monitors = await availableMonitors();
          const monitor = monitors.find((item) => item.name === position.monitorId) ?? monitors[0];
          if (monitor) {
            const scale = monitor.scaleFactor;
            const minX = monitor.workArea.position.x / scale;
            const minY = monitor.workArea.position.y / scale;
            const maxX =
              (monitor.workArea.position.x + monitor.workArea.size.width) / scale -
              256 * loaded.pet.scale;
            const maxY =
              (monitor.workArea.position.y + monitor.workArea.size.height) / scale -
              256 * loaded.pet.scale;
            await appWindow.setPosition(
              new LogicalPosition(
                Math.max(minX, Math.min(maxX, position.x)),
                Math.max(minY, Math.min(maxY, position.y)),
              ),
            );
          }
        }
      }
    });
    const handleSettings = (event: Event) =>
      setSettings((event as CustomEvent<AppSettings>).detail);
    window.addEventListener("maodie:settings", handleSettings);
    let unlistenSettings: (() => void) | undefined;
    let unlistenChat: (() => void) | undefined;
    void listen<AppSettings>("settings://changed", ({ payload }) => setSettings(payload)).then(
      (dispose) => (unlistenSettings = dispose),
    );
    void listen("chat://closed", () => dispatch({ type: "CHAT_CLOSE" })).then(
      (dispose) => (unlistenChat = dispose),
    );
    return () => {
      window.removeEventListener("maodie:settings", handleSettings);
      unlistenSettings?.();
      unlistenChat?.();
    };
  }, [appWindow, dispatch]);

  useEffect(() => {
    scheduler.cancel();
    if (!machine.mode && ["sitting", "walking", "sleeping"].includes(machine.visual)) scheduleIdle();
    return () => scheduler.cancel();
  }, [machine.mode, machine.visual, scheduleIdle, scheduler]);

  useEffect(() => {
    if (machine.visual !== "walking" || machine.mode) return;
    setDirection(machine.direction);
    return startWalking(machine.direction, settings, setDirection);
  }, [machine.direction, machine.mode, machine.visual, settings]);

  useEffect(() => {
    void Promise.all([
      appWindow.setAlwaysOnTop(settings.pet.alwaysOnTop),
      appWindow.setSize(new LogicalSize(256 * settings.pet.scale, 256 * settings.pet.scale)),
    ]).catch(() => undefined);
  }, [appWindow, settings.pet.alwaysOnTop, settings.pet.scale]);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void getCurrentWebview()
      .onDragDropEvent((event) => {
        const payload = event.payload;
        if (payload.type === "enter") {
          scheduler.cancel();
          dispatch({ type: "FILE_DRAG_ENTER", paths: payload.paths });
        } else if (payload.type === "leave") {
          dispatch({ type: "FILE_DRAG_LEAVE" });
        } else if (payload.type === "drop") {
          const paths = deduplicatePaths(payload.paths);
          dispatch({ type: "FILE_DROP", paths });
          void invoke<TrashBatchResult>("move_paths_to_trash", { paths })
            .then((result) => {
              setToast(summarizeTrashResult(result));
              dispatch(
                result.succeeded > 0
                  ? { type: "FILE_TRASH_SUCCESS", count: result.succeeded }
                  : {
                      type: "FILE_TRASH_FAILURE",
                      message: result.errors[0]?.message ?? "投喂失败",
                    },
              );
            })
            .catch((error) => {
              setToast(`投喂失败：${String(error)}`);
              dispatch({ type: "FILE_TRASH_FAILURE", message: String(error) });
            });
        }
      })
      .then((dispose) => {
        unlisten = dispose;
      })
      .catch(() => undefined);
    return () => unlisten?.();
  }, [dispatch, scheduler]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 4_000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (machine.mode !== "chat_open") return;
    void invoke("toggle_chat_window")
      .then(async () => {
        const chat = (await getAllWindows()).find((window) => window.label === "chat");
        if (!chat) return;
        const [position, size, chatSize, scaleFactor, monitors] = await Promise.all([
          appWindow.outerPosition(),
          appWindow.outerSize(),
          chat.outerSize(),
          appWindow.scaleFactor(),
          availableMonitors(),
        ]);
        const monitor =
          monitors.find(
            (item) =>
              position.x >= item.workArea.position.x &&
              position.x < item.workArea.position.x + item.workArea.size.width &&
              position.y >= item.workArea.position.y &&
              position.y < item.workArea.position.y + item.workArea.size.height,
          ) ?? monitors[0];
        if (!monitor) return;
        const work = monitor.workArea;
        let x = (position.x + size.width + 12 * scaleFactor) / scaleFactor;
        const y = (position.y + size.height - chatSize.height) / scaleFactor;
        const minX = work.position.x / scaleFactor;
        const minY = work.position.y / scaleFactor;
        const maxX = (work.position.x + work.size.width - chatSize.width) / scaleFactor;
        const maxY = (work.position.y + work.size.height - chatSize.height) / scaleFactor;
        if (x > maxX) x = (position.x - chatSize.width - 12 * scaleFactor) / scaleFactor;
        await chat.setPosition(
          new LogicalPosition(Math.max(minX, Math.min(maxX, x)), Math.max(minY, Math.min(maxY, y))),
        );
      })
      .catch(() => undefined);
  }, [appWindow, machine.mode]);

  const savePosition = useCallback(async () => {
    if (!settings.pet.savePosition) return;
    try {
      const [position, scaleFactor] = await Promise.all([
        appWindow.outerPosition(),
        appWindow.scaleFactor(),
      ]);
      await savePetPosition({
        monitorId: (await currentMonitor())?.name ?? undefined,
        x: position.x / scaleFactor,
        y: position.y / scaleFactor,
        scaleFactorAtSave: scaleFactor,
      });
    } catch {
      // Browser preview has no native window position.
    }
  }, [appWindow, settings.pet.savePosition]);

  const onPointerDown = (event: React.PointerEvent) => {
    if (event.button !== 0) return;
    pointerStart.current = { x: event.clientX, y: event.clientY, time: performance.now() };
    dragStarted.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    if (!pointerStart.current || dragStarted.current) return;
    const end = { x: event.clientX, y: event.clientY, time: performance.now() };
    if (classifyGesture(pointerStart.current, end) === "drag") {
      dragStarted.current = true;
      scheduler.cancel();
      dispatch({ type: "PET_DRAG_START" });
      void appWindow
        .startDragging()
        .catch(() => undefined)
        .finally(() => {
          pointerStart.current = undefined;
          dragStarted.current = false;
          dispatch({ type: "PET_DRAG_END" });
          void savePosition();
        });
    }
  };

  const onPointerUp = (event: React.PointerEvent) => {
    if (!pointerStart.current) return;
    const end = { x: event.clientX, y: event.clientY, time: performance.now() };
    if (dragStarted.current) {
      dispatch({ type: "PET_DRAG_END" });
      void savePosition();
    } else if (classifyGesture(pointerStart.current, end) === "click") {
      scheduler.cancel();
      dispatch({ type: "LEFT_CLICK", random: Math.random() });
    }
    pointerStart.current = undefined;
    dragStarted.current = false;
  };

  const onPointerCancel = () => {
    if (!dragStarted.current) pointerStart.current = undefined;
  };

  const onContextMenu = (event: React.MouseEvent) => {
    event.preventDefault();
    scheduler.cancel();
    if (machine.mode === "chat_open") void invoke("toggle_chat_window");
    dispatch({ type: "RIGHT_CLICK" });
  };

  return (
    <main
      className={`pet-window ${machine.mode === "file_drag_hover" ? "is-drop-target" : ""}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onContextMenu={onContextMenu}
    >
      <PetSprite
        state={machine.visual}
        direction={direction}
        fpsMultiplier={settings.appearance.animationFpsMultiplier}
        onComplete={(state) => dispatch({ type: "ANIMATION_COMPLETE", state })}
      />
      <DropOverlay visible={machine.mode === "file_drag_hover" && settings.appearance.showFeedHint} />
      {toast && <div className="toast">{toast}</div>}
    </main>
  );
}
