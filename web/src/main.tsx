import React from "react";
import { createRoot } from "react-dom/client";
import { Crown, Loader2, X } from "lucide-react";
import { api, apiUrl, streamChat, streamCourtChat, summarizeCourtChat as summarizeCourtChatApi } from "./api";
import { AppointmentDrawer, ArmyDrawer, BuildingDrawer, CourtDrawer, EconomyDrawer, HaremDrawer, RegionDetailModal, RegionDrawer } from "./components/drawers";
import { ExtractionModal } from "./components/extraction";
import { GameMenuModal } from "./components/gameMenu";
import { BudgetHover, CommandSlot, FullscreenModal, HUD_BG, HUD_SLOTS, LegacyBar, LongGoalsModal, QuadFrame } from "./components/hud";
import { GrandMap, NodeIntel } from "./components/map";
import { MenuPage } from "./components/menuPage";
import { ChatModal, ClosedIssuesModal, EdictModal, EndingModal, HistoryModal, ReportModal, SecretOrdersModal, StateModal, filterConsorts, filterMinisters } from "./components/modals";
import { SituationDrawer, SituationPanel } from "./components/situation";
import { getMapIntelStyle, refreshLabelMaps, scoreTone } from "./format";
import { forwardSteamEvents, type SteamEvent } from "./steamEvents";
import type { AppView, ChatMessage, ClosedIssue, CourtChatMessage, CourtChatResponse, Directive, GameState, MenuStatus, Minister, ModalName, PendingDecision, SecretOrder, StructuredDirective, StructuredDirectiveTemplate, Suggestion } from "./types";
import "./styles.css";

function App() {
  const [appView, setAppView] = React.useState<AppView>("menu");
  const [menuStatus, setMenuStatus] = React.useState<MenuStatus | null>(null);
  // 新 HUD stage 实际像素尺寸（matrix3d 透视需要 px 基准）
  const hudStageRef = React.useRef<HTMLDivElement | null>(null);
  const [hudStageSize, setHudStageSize] = React.useState({ w: 0, h: 0 });
  // 用 callback ref：stage 一挂载就接 ResizeObserver，避免 effect 时机竞态导致尺寸永远 0
  const hudStageCbRef = React.useCallback((el: HTMLDivElement | null) => {
    if (hudStageRef.current && (hudStageRef.current as any).__ro) {
      ((hudStageRef.current as any).__ro as ResizeObserver).disconnect();
      delete (hudStageRef.current as any).__ro;
    }
    hudStageRef.current = el;
    if (!el) return;
    const measure = () => setHudStageSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    (el as any).__ro = ro;
  }, []);
  const [state, setState] = React.useState<GameState | null>(null);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string>("");
  const [mapIntelOpen, setMapIntelOpen] = React.useState(false);
  const [situationDrawerOpen, setSituationDrawerOpen] = React.useState(false);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [haremDrawerOpen, setHaremDrawerOpen] = React.useState(false);
  const [armyDrawerOpen, setArmyDrawerOpen] = React.useState(false);
  const [regionDrawerOpen, setRegionDrawerOpen] = React.useState(false);
  const [buildingDrawerOpen, setBuildingDrawerOpen] = React.useState(false);
  const [economyDrawerOpen, setEconomyDrawerOpen] = React.useState(false);
  const [appointmentDrawerOpen, setAppointmentDrawerOpen] = React.useState(false);
  const [selectedRegionId, setSelectedRegionId] = React.useState<string>("");
  const [selectedArmyId, setSelectedArmyId] = React.useState<string>("");
  const [ministerGroup, setMinisterGroup] = React.useState("内阁+六部");
  const [haremGroup, setHaremGroup] = React.useState("全部");
  const [selectedMinister, setSelectedMinister] = React.useState<string>("");
  const [temporaryActiveMinister, setTemporaryActiveMinister] = React.useState<Minister | null>(null);
  const [activeModal, setActiveModal] = React.useState<ModalName>("none");
  const [chat, setChat] = React.useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = React.useState<Suggestion[]>([]);
  const [pendingUserMessage, setPendingUserMessage] = React.useState("");
  const [streamingMinisterMessage, setStreamingMinisterMessage] = React.useState("");
  const [chatNotice, setChatNotice] = React.useState("");
  const [courtChatHistory, setCourtChatHistory] = React.useState<CourtChatMessage[]>([]);
  const [courtChatInput, setCourtChatInput] = React.useState("");
  const [courtChatBusy, setCourtChatBusy] = React.useState(false);
  const [courtChatError, setCourtChatError] = React.useState("");
  const [courtChatBubbles, setCourtChatBubbles] = React.useState<Record<string, string>>({});
  const [courtChatPanelOpen, setCourtChatPanelOpen] = React.useState(false);
  const [courtChatLiveMessages, setCourtChatLiveMessages] = React.useState<CourtChatMessage[]>([]);
  const [courtChatSelectedMinisters, setCourtChatSelectedMinisters] = React.useState<string[]>([]);
  const [courtChatDecision, setCourtChatDecision] = React.useState<CourtChatMessage | null>(null);
  const [courtChatStreamSpeed, setCourtChatStreamSpeed] = React.useState<number>(() => {
    const saved = Number(localStorage.getItem("courtChatStreamSpeed") || "3");
    return Number.isFinite(saved) ? Math.min(5, Math.max(1, saved)) : 3;
  });
  const courtChatDeltaQueueRef = React.useRef<{ speaker: string; delta: string }[]>([]);
  const courtChatDrainTimerRef = React.useRef<number | null>(null);
  const courtChatAbortRef = React.useRef<AbortController | null>(null);
  const courtChatBubbleTimerRef = React.useRef<number | null>(null);
  const [composerHint, setComposerHint] = React.useState("");
  const [input, setInput] = React.useState("");
  const [directiveText, setDirectiveText] = React.useState("");
  const [structuredDirectiveTemplates, setStructuredDirectiveTemplates] = React.useState<StructuredDirectiveTemplate[]>([]);
  const [editingDirectiveId, setEditingDirectiveId] = React.useState<number | null>(null);
  const [editingDirectiveText, setEditingDirectiveText] = React.useState("");
  const [decree, setDecree] = React.useState("");
  const [report, setReport] = React.useState("");
  const [gazetteReport, setGazetteReport] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [settleStage, setSettleStage] = React.useState("");
  const [settleThinking, setSettleThinking] = React.useState("");
  const [settleNarrative, setSettleNarrative] = React.useState("");
  const [closedShown, setClosedShown] = React.useState<number>(() => {
    const raw = sessionStorage.getItem("closedShownTurn");
    return raw ? Number(raw) : -1;
  });
  const [closedModal, setClosedModal] = React.useState<ClosedIssue[]>([]);
  const [gazetteShown, setGazetteShown] = React.useState<number>(-1);
  // 结局页本次加载是否已被玩家关掉（关掉后让位邸报，刷新复位重弹）。
  const [endingDismissed, setEndingDismissed] = React.useState(false);
  const [secretOrders, setSecretOrders] = React.useState<SecretOrder[]>([]);
  const [secretOrderShown, setSecretOrderShown] = React.useState<number>(-1);
  // 作弊控制台（Ctrl+~）：cheatDirective 暂存强制结算项，下次颁诏随结算一次性穿入。
  const [cheatOpen, setCheatOpen] = React.useState(false);
  const [cheatDirective, setCheatDirective] = React.useState("");
  // HITL 决策点：颁诏推演若出遇阻纠偏，暂停弹窗逐个亲裁，裁完续跑结算。
  const [pendingDecisions, setPendingDecisions] = React.useState<PendingDecision[]>([]);
  const settling = busy === "月末结算";

  const loadState = React.useCallback(async () => {
    const data = await api<GameState>("/api/game/state");
    refreshLabelMaps(data);
    setState(data);
    setSelectedNodeId((current) => current || data.map_nodes[0]?.id || "");
    setDecree(data.last_decree || "");
    setReport(data.last_report || "");
  }, []);

  const loadStructuredDirectiveTemplates = React.useCallback(async () => {
    const data = await api<{ templates: StructuredDirectiveTemplate[] }>("/api/structured_directives/templates");
    setStructuredDirectiveTemplates(data.templates || []);
  }, []);

  const loadMinisterChat = React.useCallback(async (ministerName: string) => {
    const data = await api<{ minister: Minister; history: ChatMessage[]; suggestions: Suggestion[] }>(`/api/ministers/${encodeURIComponent(ministerName)}/chat`);
    setState((currentState) => {
      const allKnown = [
        ...(currentState?.ministers || []),
        ...(currentState?.consorts || []),
      ];
      setTemporaryActiveMinister(allKnown.some((m) => m.name === data.minister.name) ? null : data.minister);
      return currentState;
    });
    setChat(data.history);
    setSuggestions(data.suggestions);
  }, []);

  const uploadPortrait = React.useCallback(async (ministerName: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(apiUrl(`/api/consorts/${encodeURIComponent(ministerName)}/portrait`), {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    await loadState();  // 重新拉 state，新 portrait_id 流回卡片
  }, [loadState]);

  const refreshCourtChat = React.useCallback(async () => {
    const data = await api<CourtChatResponse>("/api/court_chat");
    setCourtChatHistory(data.history || []);
  }, []);

  const appendCourtChatDelta = React.useCallback((speaker: string, delta: string) => {
    if (!speaker || !delta) return;
    const cleanDelta = delta.replace(/^\s*>+\s*/, "").replace(/\s*>+\s*$/, "");
    if (!cleanDelta) return;
    setCourtChatBubbles((current) => ({ ...current, [speaker]: `${(current[speaker] || "")}${cleanDelta}`.slice(-42) }));
    setCourtChatLiveMessages((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last && last.role === "minister" && last.speaker === speaker) {
        const content = `${last.content || ""}${cleanDelta}`.replace(/^\s+/, "");
        next[next.length - 1] = { ...last, content, displayContent: content };
        return next;
      }
      return [...next, { role: "minister", speaker, content: cleanDelta, displayContent: cleanDelta }];
    });
  }, []);

  const courtChatDeltaDelay = React.useMemo(() => {
    const delays: Record<number, number> = { 1: 170, 2: 120, 3: 85, 4: 45, 5: 0 };
    return delays[courtChatStreamSpeed] ?? 85;
  }, [courtChatStreamSpeed]);

  const updateCourtChatStreamSpeed = React.useCallback((value: number, persistLocal = true) => {
    const next = Math.min(5, Math.max(1, Math.round(value)));
    setCourtChatStreamSpeed(next);
    if (persistLocal) {
      localStorage.setItem("courtChatStreamSpeed", String(next));
    }
  }, []);

  const drainCourtChatDeltas = React.useCallback(() => {
    const next = courtChatDeltaQueueRef.current.shift();
    if (next) {
      appendCourtChatDelta(next.speaker, next.delta);
    }
    if (courtChatDeltaQueueRef.current.length) {
      courtChatDrainTimerRef.current = window.setTimeout(drainCourtChatDeltas, courtChatDeltaDelay);
    } else {
      courtChatDrainTimerRef.current = null;
    }
  }, [appendCourtChatDelta, courtChatDeltaDelay]);

  const queueCourtChatDelta = React.useCallback((speaker: string, delta: string) => {
    if (!speaker || !delta) return;
    courtChatDeltaQueueRef.current.push({ speaker, delta });
    if (courtChatDrainTimerRef.current === null) {
      courtChatDrainTimerRef.current = window.setTimeout(drainCourtChatDeltas, courtChatDeltaDelay);
    }
  }, [courtChatDeltaDelay, drainCourtChatDeltas]);

  const flushCourtChatDeltas = React.useCallback(() => {
    while (courtChatDeltaQueueRef.current.length) {
      const next = courtChatDeltaQueueRef.current.shift();
      if (next) appendCourtChatDelta(next.speaker, next.delta);
    }
    if (courtChatDrainTimerRef.current !== null) {
      window.clearTimeout(courtChatDrainTimerRef.current);
      courtChatDrainTimerRef.current = null;
    }
  }, [appendCourtChatDelta]);

  React.useEffect(() => {
    return () => {
      if (courtChatDrainTimerRef.current !== null) {
        window.clearTimeout(courtChatDrainTimerRef.current);
      }
      if (courtChatBubbleTimerRef.current !== null) {
        window.clearTimeout(courtChatBubbleTimerRef.current);
      }
      courtChatDrainTimerRef.current = null;
      courtChatBubbleTimerRef.current = null;
      courtChatDeltaQueueRef.current = [];
    };
  }, []);

  const refreshCourtChatWithError = React.useCallback(() => {
    refreshCourtChat()
      .then(() => setCourtChatError(""))
      .catch(() => {
        // 旧后端未重启或接口暂不可用时，不要用大错误牌挡住朝堂。
      });
  }, [refreshCourtChat]);

  const refreshMenuStatus = React.useCallback(async () => {
    const s = await api<MenuStatus>("/api/menu/status");
    setMenuStatus(s);
    const configuredSpeed = Number(s.game_settings?.court_chat_stream_speed);
    if (Number.isFinite(configuredSpeed)) {
      updateCourtChatStreamSpeed(configuredSpeed, false);
    }
    return s;
  }, [updateCourtChatStreamSpeed]);

  React.useEffect(() => {
    refreshMenuStatus()
      .then((s) => {
        if (s.has_running_game) {
          setAppView("game");
          loadState().catch((err) => setError(err.message));
          loadStructuredDirectiveTemplates().catch(() => {});
        }
      })
      .catch((err) => setError(err.message));
  }, [refreshMenuStatus, loadState, loadStructuredDirectiveTemplates]);

  const enterGameAfterMenu = React.useCallback(async () => {
    setAppView("game");
    await loadState();
    await loadStructuredDirectiveTemplates();
  }, [loadState, loadStructuredDirectiveTemplates]);

  const exitToMenu = React.useCallback(async () => {
    await api("/api/menu/exit_to_menu", { method: "POST" });
    setState(null);
    setAppView("menu");
    await refreshMenuStatus();
  }, [refreshMenuStatus]);

  React.useEffect(() => {
    if (!state) return;
    const closed = state.closed_this_turn || [];
    const currentTurn = state.turn.turn;
    if (closed.length && currentTurn !== closedShown) {
      setClosedModal(closed);
      setClosedShown(currentTurn);
      sessionStorage.setItem("closedShownTurn", String(currentTurn));
    }
  }, [state, closedShown]);

  // 新回合进入时拉取全部密令，更新 HUD 数量；详情由玩家自行点“密令”查看。
  React.useEffect(() => {
    if (!state) return;
    const currentTurn = state.turn.turn;
    if (currentTurn === secretOrderShown) return;
    api<{ orders: SecretOrder[] }>("/api/secret_orders")
      .then(({ orders }) => {
        setSecretOrders(orders);
        setSecretOrderShown(currentTurn);
      })
      .catch(() => {/* 失败静默 */});
  }, [state?.turn.turn]);

  // 结局已触发：每次进页面/刷新都自动弹结局结算页。玩家点关闭后（endingDismissed）
  // 本次加载让位给盘面/邸报，可继续看局；刷新即复位重弹。
  React.useEffect(() => {
    if (!state || !state.ending) return;
    if (endingDismissed) return;
    setActiveModal("ending");
  }, [state, endingDismissed]);

  // 刷新恢复：若回合停在 awaiting_decision 且有未裁决策点，自动重弹决策弹窗。
  React.useEffect(() => {
    if (!state) return;
    if (state.turn.phase !== "awaiting_decision") return;
    const decisions = state.pending_decisions || [];
    if (decisions.length === 0) return;
    setPendingDecisions((prev) => (prev.length ? prev : decisions));
  }, [state]);

  // 每次进入页面/换回合都弹上回合邸报。不持久化记录——刷新即重新弹。
  // 同一加载周期内同一回合不重复弹（gazetteShown 用 React state，刷新后回到 -1）。
  React.useEffect(() => {
    if (!state) return;
    // 结局页未关掉时让位给它；玩家关掉后（endingDismissed）邸报照常。
    if (state.ending && !endingDismissed) return;
    const currentTurn = state.turn.turn;
    const summary = (state.previous_summary || "").trim();
    if (!summary) return;
    if (summary.startsWith("登基伊始")) return;
    if (currentTurn === gazetteShown) return;
    setGazetteReport(summary);
    setActiveModal("report");
    setGazetteShown(currentTurn);
  }, [state, gazetteShown, endingDismissed]);

  React.useEffect(() => {
    if (!selectedMinister) {
      setChat([]);
      setSuggestions([]);
      setPendingUserMessage("");
      setStreamingMinisterMessage("");
      setChatNotice("");
      setComposerHint("");
      return;
    }
    setChat([]);
    setSuggestions([]);
    setPendingUserMessage("");
    setStreamingMinisterMessage("");
    setComposerHint("");
    loadMinisterChat(selectedMinister).catch((err) => setError(err.message));
  }, [selectedMinister, loadMinisterChat]);

  // 全局 ESC：按 z-index 优先级，最前面的弹窗先关；空闲时打开游戏菜单。
  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (settling) return;
      if (activeModal === "menu") {
        setActiveModal("none");
      } else if (activeModal === "chat" || activeModal === "edict" || activeModal === "state" || activeModal === "history" || activeModal === "report" || activeModal === "secret_orders" || activeModal === "long_goals" || activeModal === "extraction" || activeModal === "ending") {
        // 召对/诏书等全屏弹窗最优先
        setActiveModal("none");
      } else if (drawerOpen) {
        setDrawerOpen(false);
      } else if (haremDrawerOpen) {
        setHaremDrawerOpen(false);
      } else if (armyDrawerOpen) {
        setArmyDrawerOpen(false);
      } else if (regionDrawerOpen) {
        setRegionDrawerOpen(false);
      } else if (buildingDrawerOpen) {
        setBuildingDrawerOpen(false);
      } else if (economyDrawerOpen) {
        setEconomyDrawerOpen(false);
      } else if (appointmentDrawerOpen) {
        setAppointmentDrawerOpen(false);
      } else if (situationDrawerOpen) {
        setSituationDrawerOpen(false);
      } else if (mapIntelOpen) {
        setMapIntelOpen(false);
      } else {
        setActiveModal("menu");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    activeModal,
    appointmentDrawerOpen,
    armyDrawerOpen,
    buildingDrawerOpen,
    drawerOpen,
    economyDrawerOpen,
    haremDrawerOpen,
    mapIntelOpen,
    regionDrawerOpen,
    settling,
    situationDrawerOpen,
  ]);

  // 作弊控制台：Ctrl+~（或 Ctrl+`）切换显隐。强制结算唯一入口。
  React.useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.ctrlKey && (event.key === "~" || event.key === "`")) {
        event.preventDefault();
        setCheatOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (appView === "menu") {
    return (
      <MenuPage
        status={menuStatus}
        onRefresh={refreshMenuStatus}
        onEnterGame={enterGameAfterMenu}
        error={error}
        setError={setError}
      />
    );
  }

  if (!state) {
    return (
      <div className="loading-screen">
        <div className="loading-panel">
          <Crown size={28} />
          <p>正在启封奏牍与山河舆图...</p>
        </div>
      </div>
    );
  }

  const powerById = new Map((state.powers || []).map((power) => [power.id, power]));
  const mapNodes = state.map_nodes.map((node) => {
    const powerId = node.region?.controlled_by;
    return powerId ? { ...node, power: powerById.get(powerId) } : node;
  });
  const selectedNode = mapNodes.find((node) => node.id === selectedNodeId) || mapNodes[0];
  const rosterMinisters = [...(state.ministers || []), ...(state.archived_ministers || [])];
  const ministers = filterMinisters(rosterMinisters, ministerGroup);
  const activeCourtMinisterNames = ministers.filter(canAttendCourtChat).map((m) => m.name);
  const effectiveCourtChatSelectedMinisters = courtChatSelectedMinisters.filter((name) => activeCourtMinisterNames.includes(name));
  const courtChatRosterSelection = effectiveCourtChatSelectedMinisters;
  const consorts = filterConsorts(state.consorts || [], haremGroup);
  const allCharacters = [...rosterMinisters, ...(state.consorts || [])];
  const activeMinister = selectedMinister
    ? allCharacters.find((m) => m.name === selectedMinister) || temporaryActiveMinister
    : null;
  const mapIntelStyle = selectedNode ? getMapIntelStyle(selectedNode) : undefined;

  const openChat = (minister: Minister) => {
    const switchingMinister = selectedMinister !== minister.name;
    if (switchingMinister) {
      setChat([]);
      setSuggestions([]);
      setTemporaryActiveMinister(null);
    }
    setSelectedMinister(minister.name);
    setActiveModal("chat");
    setError("");
    setComposerHint("");
    setChatNotice("");
    setPendingUserMessage("");
    setStreamingMinisterMessage("");
    loadMinisterChat(minister.name).catch((err) => setError(err.message));
  };

  const selectMapNode = (nodeId: string) => {
    setSelectedNodeId(nodeId);
    setMapIntelOpen(true);
  };

  const sendChat = async (text = input) => {
    if (busy) return;
    if (!activeMinister) return;
    const message = text.trim();
    if (activeMinister.status === "dead" || activeMinister.status === "offstage") {
      setComposerHint(`${activeMinister.name}${activeMinister.status_label || activeMinister.status}，不能继续召对。`);
      return;
    }
    if (!message) {
      setComposerHint("请先问话或点一个奏对题目");
      return;
    }

    const fromComposer = text === input;
    setPendingUserMessage(message);
    setStreamingMinisterMessage("");
    setBusy("大臣思索中");
    setError("");
    setComposerHint("");
    setChatNotice("");
    if (fromComposer) {
      setInput("");
    }
    try {
      const data = await streamChat(activeMinister.name, message, (delta) => {
        setStreamingMinisterMessage((current) => current + delta);
      });
      setPendingUserMessage("");
      setStreamingMinisterMessage("");
      setChat(data.history);
      setSuggestions(data.suggestions);
      setState((current) => (current ? { ...current, directives: data.directives, pending_count: data.pending_count ?? current.pending_count } : current));
      await loadState();
      // 刷新密令列表（含历史，大臣可能调了 issue_secret_order tool）
      api<{ orders: SecretOrder[] }>("/api/secret_orders")
        .then(({ orders }) => setSecretOrders(orders))
        .catch(() => {});
      if (data.secret_order_id) {
        setChatNotice(`密令已秘密交付${activeMinister.name}，编号 #${data.secret_order_id}。`);
      }
      if (data.proposed_directive) {
        setChatNotice(`${activeMinister.name}已拟旨一道，待陛下在「诏书草案」核定（准/驳）。`);
      }
      if (data.next_minister) {
        setChat([]);
        setSuggestions([]);
        setStreamingMinisterMessage("");
        setSelectedMinister(data.next_minister);
        setActiveModal("chat");
        setChatNotice(`已传${data.next_minister}入殿。`);
        loadMinisterChat(data.next_minister).catch((err) => setError(err.message));
      }
      if (data.court_action === "dismiss") {
        setPendingUserMessage("");
        setChatNotice(`${activeMinister.name}已退下。请从左侧召见下一位大臣。`);
      }
    } catch (err) {
      if (fromComposer) {
        setInput(message);
      }
      setPendingUserMessage("");
      setStreamingMinisterMessage("");
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const undoLastChat = async () => {
    if (busy || !activeMinister) return;
    setBusy("撤回上一轮召对");
    setError("");
    setChatNotice("");
    try {
      const data = await api<{ history: ChatMessage[]; suggestions: Suggestion[]; directives: Directive[]; pending_count: number }>(
        `/api/ministers/${encodeURIComponent(activeMinister.name)}/chat/undo`,
        { method: "POST" },
      );
      setChat(data.history);
      setSuggestions(data.suggestions);
      setPendingUserMessage("");
      setStreamingMinisterMessage("");
      setState((current) => (current ? { ...current, directives: data.directives, pending_count: data.pending_count } : current));
      setChatNotice("已撤回上一轮召对。");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const sendCourtChat = async (visibleMinisters: Minister[], overrideMessage?: string) => {
    const message = (overrideMessage ?? courtChatInput).trim();
    if (!message) return;
    const speakers = visibleMinisters
      .filter((m) => canAttendCourtChat(m) && courtChatRosterSelection.includes(m.name))
      .map((m) => m.name);
    if (!speakers.length) {
      setCourtChatError("朝堂当前没有可参与朝议的大臣。");
      return;
    }
    const isInterjection = courtChatBusy;
    if (isInterjection && courtChatAbortRef.current) {
      courtChatAbortRef.current.abort();
      courtChatAbortRef.current = null;
    }
    const abortController = new AbortController();
    courtChatAbortRef.current = abortController;
    setCourtChatBusy(true);
    setCourtChatError("");
    setCourtChatInput("");
    setCourtChatBubbles({});
    if (courtChatDrainTimerRef.current !== null) {
      window.clearTimeout(courtChatDrainTimerRef.current);
      courtChatDrainTimerRef.current = null;
    }
    courtChatDeltaQueueRef.current = [];
    setCourtChatDecision(null);
    setCourtChatPanelOpen(true);
    setCourtChatLiveMessages((current) => [
      ...current,
      { role: "emperor", speaker: "皇帝", content: isInterjection ? `朕打断一句：${message}` : message, displayContent: isInterjection ? `朕打断一句：${message}` : message },
    ]);
    setCourtChatHistory((current) => [...current, { role: "emperor", speaker: "皇帝", content: message }]);
    try {
      const data = await streamCourtChat(
        isInterjection ? `【皇帝插话，打断当前廷议并扭转话题】${message}` : message,
        speakers,
        () => {},
        (speaker, delta) => {
          if (!speaker || !delta) return;
          queueCourtChatDelta(speaker, delta);
        },
        (speaker) => {
          if (!speaker) return;
          flushCourtChatDeltas();
          setCourtChatLiveMessages((current) => {
            const last = current[current.length - 1];
            if (last && last.role === "minister" && last.speaker === speaker && !last.content) return current;
            return [...current, { role: "minister", speaker, content: "", displayContent: "" }];
          });
        },
        (conclusion) => {
          flushCourtChatDeltas();
          setCourtChatLiveMessages((current) => [...current, { ...conclusion, role: "conclusion" }]);
          setCourtChatDecision(conclusion.options?.length ? conclusion : null);
        },
        abortController.signal,
      );
      if (abortController.signal.aborted) return;
      flushCourtChatDeltas();
      setCourtChatHistory(data.history || []);
      if (courtChatBubbleTimerRef.current !== null) {
        window.clearTimeout(courtChatBubbleTimerRef.current);
      }
      courtChatBubbleTimerRef.current = window.setTimeout(() => {
        setCourtChatBubbles({});
        courtChatBubbleTimerRef.current = null;
      }, 7000);
    } catch (err) {
      if (abortController.signal.aborted) return;
      flushCourtChatDeltas();
      setCourtChatInput(message);
      setCourtChatError(err instanceof Error ? err.message : String(err));
    } finally {
      if (abortController.signal.aborted) {
        return;
      }
      if (courtChatAbortRef.current === abortController) {
        courtChatAbortRef.current = null;
        setCourtChatBusy(false);
      }
    }
  };

  const stopCourtChat = () => {
    if (!courtChatAbortRef.current) return;
    courtChatAbortRef.current.abort();
    courtChatAbortRef.current = null;
    if (courtChatDrainTimerRef.current !== null) {
      window.clearTimeout(courtChatDrainTimerRef.current);
      courtChatDrainTimerRef.current = null;
    }
    courtChatDeltaQueueRef.current = [];
    setCourtChatBusy(false);
    setCourtChatBubbles({});
    setCourtChatError("");
  };

  const summarizeCourtChat = async (_visibleMinisters: Minister[]) => {
    if (courtChatBusy) return;
    const visibleMessages = courtChatLiveMessages
      .map((message) => ({ ...message, content: message.displayContent ?? message.content }))
      .filter((message) => message.content.trim());
    if (!visibleMessages.length) {
      setCourtChatError("当前屏幕没有可总结的朝会内容。");
      return;
    }
    setCourtChatBusy(true);
    setCourtChatError("");
    try {
      const summary = await summarizeCourtChatApi(visibleMessages);
      setCourtChatLiveMessages((current) => [...current, summary]);
      setCourtChatDecision(summary.options?.length ? summary : null);
      await refreshCourtChat();
    } catch (err) {
      setCourtChatError(err instanceof Error ? err.message : String(err));
    } finally {
      setCourtChatBusy(false);
    }
  };

  const createDirective = async () => {
    if (!directiveText.trim()) return;
    setBusy("登记诏书草案");
    setError("");
    try {
      const data = await api<{ directives: Directive[] }>("/api/directives", {
        method: "POST",
        body: JSON.stringify({
          text: directiveText.trim(),
        }),
      });
      setDirectiveText("");
      setState((current) => (current ? { ...current, directives: data.directives } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const chooseCourtChatDecision = async (option: string) => {
    if (!option.trim()) return;
    setBusy("登记朝议裁断");
    setError("");
    try {
      const data = await api<{ directives: Directive[] }>("/api/directives", {
        method: "POST",
        body: JSON.stringify({
          text: `朝会裁断：${option.trim()}`,
          notes: "由本月朝会结论转入草案",
        }),
      });
      setState((current) => (current ? { ...current, directives: data.directives } : current));
      setCourtChatDecision(null);
      setCourtChatPanelOpen(false);
      setDrawerOpen(false);
      setActiveModal("edict");
    } catch (err) {
      setCourtChatError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const toggleFavorite = async (minister: Minister) => {
    setBusy(minister.favorite ? "移出收藏" : "加入收藏");
    setError("");
    try {
      await api<{ favorites: string[] }>(`/api/favorites/${encodeURIComponent(minister.name)}`, {
        method: minister.favorite ? "DELETE" : "POST",
      });
      await loadState();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const archiveMinister = async (minister: Minister) => {
    if (minister.status === "active" || minister.origin !== "runtime") return;
    if (!window.confirm(`归档「${minister.name}」？归档后此人保留数据库记录，但不再进入名册、召对候选和月末推演。`)) return;
    setBusy("归档人物");
    setError("");
    try {
      await api(`/api/ministers/${encodeURIComponent(minister.name)}/archive`, {
        method: "POST",
      });
      setSelectedMinister("");
      setTemporaryActiveMinister(null);
      setActiveModal("none");
      await loadState();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const restoreMinister = async (minister: Minister) => {
    if (!minister.archived) return;
    setBusy("恢复人物");
    setError("");
    try {
      await api(`/api/ministers/${encodeURIComponent(minister.name)}/restore`, {
        method: "POST",
      });
      await loadState();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const startEditDirective = (directive: Directive) => {
    setEditingDirectiveId(directive.id);
    setEditingDirectiveText(directive.text);
  };

  const cancelEditDirective = () => {
    setEditingDirectiveId(null);
    setEditingDirectiveText("");
  };

  const saveDirective = async (directive: Directive) => {
    if (!editingDirectiveText.trim()) return;
    setBusy("修改草案");
    setError("");
    try {
      const data = await api<{ directives: Directive[] }>(`/api/directives/${directive.id}`, {
        method: "PATCH",
        body: JSON.stringify({ text: editingDirectiveText.trim() }),
      });
      setState((current) => (current ? { ...current, directives: data.directives } : current));
      cancelEditDirective();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const deleteDirective = async (directiveId: number) => {
    setBusy("删除草案");
    setError("");
    try {
      const data = await api<{ directives: Directive[] }>(`/api/directives/${directiveId}`, { method: "DELETE" });
      setState((current) => (current ? { ...current, directives: data.directives } : current));
      if (editingDirectiveId === directiveId) {
        cancelEditDirective();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const saveStructuredDirective = async (
    directive: StructuredDirective | null,
    templateId: string,
    fields: Record<string, string>,
  ) => {
    setBusy(directive ? "修改固定指令" : "新增固定指令");
    setError("");
    try {
      const data = await api<{ structured_directives: StructuredDirective[] }>(
        directive ? `/api/structured_directives/${directive.id}` : "/api/structured_directives",
        {
          method: directive ? "PATCH" : "POST",
          body: JSON.stringify({ template_id: templateId, fields }),
        },
      );
      setState((current) => (current ? { ...current, structured_directives: data.structured_directives } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setBusy("");
    }
  };

  const deleteStructuredDirective = async (directiveId: number) => {
    setBusy("删除固定指令");
    setError("");
    try {
      const data = await api<{ structured_directives: StructuredDirective[] }>(`/api/structured_directives/${directiveId}`, { method: "DELETE" });
      setState((current) => (current ? { ...current, structured_directives: data.structured_directives } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const confirmDirective = async (directiveId: number) => {
    setBusy("核定大臣拟旨");
    setError("");
    try {
      const data = await api<{ directives: Directive[]; pending_count: number }>(`/api/directives/${directiveId}/confirm`, { method: "POST" });
      setState((current) => (current ? { ...current, directives: data.directives, pending_count: data.pending_count } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const rejectDirective = async (directiveId: number) => {
    setBusy("驳回大臣拟旨");
    setError("");
    try {
      const data = await api<{ directives: Directive[]; pending_count: number }>(`/api/directives/${directiveId}/reject`, { method: "POST" });
      setState((current) => (current ? { ...current, directives: data.directives, pending_count: data.pending_count } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const confirmAllDirectives = async () => {
    const pending = (state?.directives || []).filter((d) => d.status === "pending");
    if (!pending.length) return;
    setBusy("一键准奏大臣拟旨");
    setError("");
    try {
      let latest: { directives: Directive[]; pending_count: number } | null = null;
      for (const directive of pending) {
        latest = await api<{ directives: Directive[]; pending_count: number }>(`/api/directives/${directive.id}/confirm`, { method: "POST" });
      }
      if (latest) {
        const data = latest;
        setState((current) => (current ? { ...current, directives: data.directives, pending_count: data.pending_count } : current));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const generateDecree = async (force = false) => {
    setBusy("拟写正式诏书");
    setError("");
    try {
      const data = await api<{ decree: string }>("/api/decree/write", {
        method: "POST",
        body: JSON.stringify({ force }),
      });
      setDecree(data.decree);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const writeDecree = async () => {
    if ((decree || state?.last_decree || "").trim()) {
      setDecree((current) => current || state?.last_decree || "");
      return;
    }
    await generateDecree();
  };

  const rewriteDecree = async () => {
    await generateDecree(true);
  };

  const saveDecree = async (text: string) => {
    setBusy("存改诏书");
    setError("");
    try {
      const data = await api<{ decree: string }>("/api/decree", {
        method: "PATCH",
        body: JSON.stringify({ decree: text }),
      });
      setDecree(data.decree);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  };

  const resetDecree = () => {
    // 返工：丢弃当前诏文回到御案理政幕。后端旧诏文留着无妨，重新生成即覆盖。
    setDecree("");
    setError("");
  };

  // 颁诏/续裁共用：消费 SSE 推演流，stage/thinking/text 实时更新进度区，
  // 返回结束态：done（已结算）/ decisions（暂停待裁）/ error。
  const consumeSettleStream = async (
    response: Response
  ): Promise<{ kind: "done" | "decisions" | "error"; data: any }> => {
    if (!response.ok || !response.body) {
      throw new Error(`颁诏失败：HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        let evName = "";
        let dataRaw = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) evName = line.slice(7).trim();
          else if (line.startsWith("data: ")) dataRaw += line.slice(6);
        }
        if (!evName || !dataRaw) continue;
        let data: any = {};
        try { data = JSON.parse(dataRaw); } catch { continue; }
        if (evName === "stage") setSettleStage(data.content || "");
        else if (evName === "thinking") setSettleThinking((prev) => prev + (data.content || ""));
        else if (evName === "text") setSettleNarrative((prev) => prev + (data.content || ""));
        else if (evName === "error") return { kind: "error", data: data.message || "颁诏失败。" };
        else if (evName === "decisions") return { kind: "decisions", data };
        else if (evName === "done") return { kind: "done", data };
      }
    }
    return { kind: "error", data: "推演流意外中断。" };
  };

  const issueDecree = async () => {
    setBusy("月末结算");
    setSettleStage("");
    setSettleThinking("");
    setSettleNarrative("");
    setError("");
    try {
      // 作弊强制结算项随颁诏一次性穿入；发出即清空，绝不跨回合。
      const cheatPayload = cheatDirective.trim();
      const response = await fetch(apiUrl("/api/decree/issue/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cheat: cheatPayload }),
      });
      if (cheatPayload) {
        setCheatDirective("");
      }
      const outcome = await consumeSettleStream(response);
      if (outcome.kind === "error") {
        setError(typeof outcome.data === "string" ? outcome.data : (outcome.data.message || "颁诏失败。"));
        setBusy("");
        return;
      }
      if (outcome.kind === "decisions") {
        // 出遇阻纠偏：暂停弹窗逐个亲裁，裁完调 submitDecisions 续跑结算。
        setPendingDecisions(outcome.data.decisions || []);
        setBusy("");
        return;
      }
      await forwardSteamEvents(outcome.data);
      // 结算完成：强制整页刷新，草案/对话/局势/closed 弹窗全部按新 state 重新初始化
      window.location.reload();
      return;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy("");
    }
  };

  // 皇帝亲裁完所有决策点：续跑 phase2 结算。choices 按决策点 idx 顺序。
  const submitDecisions = async (choices: { label?: string; hint?: string; note?: string }[]) => {
    setPendingDecisions([]);
    setBusy("月末结算");
    setSettleStage("圣意亲裁，续推时局");
    setSettleThinking("");
    setSettleNarrative("");
    setError("");
    try {
      const response = await fetch(apiUrl("/api/decree/resolve_decisions/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choices }),
      });
      const outcome = await consumeSettleStream(response);
      if (outcome.kind === "error") {
        setError(typeof outcome.data === "string" ? outcome.data : (outcome.data.message || "结算失败。"));
        setBusy("");
        return;
      }
      await forwardSteamEvents(outcome.data);
      window.location.reload();
      return;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy("");
    }
  };

  const guardClose = (fn: () => void) => () => {
    if (settling) return;
    fn();
  };

  const activeDrawerKey =
    drawerOpen ? "court" :
    haremDrawerOpen ? "harem" :
    armyDrawerOpen ? "army" :
    regionDrawerOpen ? "region" :
    buildingDrawerOpen ? "building" :
    economyDrawerOpen ? "economy" :
    appointmentDrawerOpen ? "appointment" : "";
  const navHandlers = {
    court: () => setDrawerOpen((v) => !v),
    harem: () => setHaremDrawerOpen((v) => !v),
    army: () => setArmyDrawerOpen((v) => !v),
    region: () => setRegionDrawerOpen((v) => !v),
    building: () => setBuildingDrawerOpen((v) => !v),
    economy: () => setEconomyDrawerOpen((v) => !v),
    appointment: () => setAppointmentDrawerOpen((v) => !v),
    goal: () => setActiveModal("long_goals"),
  };
  const sz = hudStageSize;
  const ready = sz.w > 0 && sz.h > 0;

  return (
    <main className="game-shell">
      <div className="hud2-stage" ref={hudStageCbRef}>
        <img className="hud2-bg" src={HUD_BG} alt="" />

        {/* 地图：透视梯形（GrandMap 已改 transform pan，兼容 matrix3d）。?flat=1 关透视调试 */}
        {ready ? (
          (typeof window !== "undefined" && new URLSearchParams(window.location.search).has("flat")) ? (
            <div className="hud2-map-quad" style={{
              position: "absolute",
              left: `${HUD_SLOTS.地图四角.tl[0]}%`, top: `${HUD_SLOTS.地图四角.tl[1]}%`,
              width: `${HUD_SLOTS.地图四角.tr[0] - HUD_SLOTS.地图四角.tl[0]}%`,
              height: `${HUD_SLOTS.地图四角.bl[1] - HUD_SLOTS.地图四角.tl[1]}%`,
            }}>
              <GrandMap nodes={mapNodes} selectedId={mapIntelOpen ? selectedNode?.id || "" : ""} onSelect={selectMapNode} />
            </div>
          ) : (
            <QuadFrame className="hud2-map-quad" quad={HUD_SLOTS.地图四角}
              stageW={sz.w} stageH={sz.h} baseW={2560} baseH={1440}>
              <GrandMap nodes={mapNodes} selectedId={mapIntelOpen ? selectedNode?.id || "" : ""} onSelect={selectMapNode} />
            </QuadFrame>
          )
        ) : null}

        {/* 局势进度：塞进左卡透视梯形 */}
        {ready ? (
          <QuadFrame className="hud2-issue-quad" quad={HUD_SLOTS.局势四角}
            stageW={sz.w} stageH={sz.h} baseW={2560} baseH={1440}>
            <SituationPanel
              issues={state.issues}
              closedIssues={state.closed_this_turn || []}
              hasLegacies={(state.legacies || []).length > 0}
              ministers={state.ministers || []}
              compact
              onOpenDrawer={() => setSituationDrawerOpen(true)}
              onChanged={() => loadState()}
            />
          </QuadFrame>
        ) : null}

        {/* 顶栏：年月 + 国库/内库 + 民心/皇威，各按坑位绝对定位 */}
        <button className="hud2-slot hud2-year" style={HUD_SLOTS.顶栏.年月}
          onClick={() => setActiveModal("state")}>
          <span className="hud2-lab">大明</span>
          <span className="hud2-val">{state.turn.year} 年 {state.turn.period} 月</span>
        </button>
        <div className="hud2-slot" style={HUD_SLOTS.顶栏.国库}>
          <BudgetHover accountName="国库" budget={state.budget["国库"]} />
        </div>
        <div className="hud2-slot" style={HUD_SLOTS.顶栏.内库}>
          <BudgetHover accountName="内库" budget={state.budget["内库"]} />
        </div>
        <div className="hud2-slot hud2-metric-pair" style={HUD_SLOTS.顶栏.民心}>
          <span className={`hud2-metric-one ${scoreTone(state.metrics["民心"], false)}`}>
            <span className="hud2-lab">民心</span><span className="hud2-val">{state.metrics["民心"]}</span>
          </span>
          <span className={`hud2-metric-one ${scoreTone(state.metrics["皇威"], false)}`}>
            <span className="hud2-lab">皇威</span><span className="hud2-val">{state.metrics["皇威"]}</span>
          </span>
        </div>
        <div className="hud2-slot hud2-legacy-slot" style={HUD_SLOTS.顶栏.皇威}>
          <LegacyBar legacies={state.legacies} />
        </div>
        <button className="hud2-menu-btn"
          title="游戏菜单" aria-label="游戏菜单" onClick={() => setActiveModal("menu")}>
          <span className="hud2-val">菜單</span>
        </button>

        {/* 右侧竖排部院导航 */}
        {([
          ["朝堂", "court", "朝堂·召见大臣"],
          ["吏部", "appointment", "官员任免"],
          ["省份", "region", "省份列表"],
          ["兵部", "army", "军队列表"],
          ["戶部", "economy", "经济面板"],
          ["工部", "building", "建筑列表"],
          ["禮部", "court", "礼部"],
          ["後宮", "harem", "后宫"],
          ["目標", "goal", "长期目标"],
        ] as const).map(([label, key, title], idx) => {
          const slotKey = (["政","吏部","省份","兵部","户部","工部","礼部","后宫","目标"] as const)[idx];
          return (
            <button key={slotKey} className={`hud2-slot hud2-nav${activeDrawerKey === key ? " active" : ""}`}
              style={HUD_SLOTS.导航[slotKey]} title={title} aria-label={title}
              onClick={(navHandlers as any)[key]}>
              {label}
            </button>
          );
        })}

        {/* 底部 5 命令物件（扣图填进木牌） */}
        <CommandSlot slotKey="奏疏" img="奏疏" badge={state.events.length}
          caption="奏疏" sub={`${state.events.length} 件待覽`} onClick={() => setActiveModal("state")} />
        <CommandSlot slotKey="邸报" img="邸报"
          caption="邸報詳明" sub="數項加減/賬目明細" onClick={() => setActiveModal("extraction")} />
        <CommandSlot slotKey="密令" img="密令"
          badge={secretOrders.filter((o) => o.status === "active" || o.status === "pending_review").length}
          caption="密令" sub="進行中密令" onClick={() => setActiveModal("secret_orders")} />
        <CommandSlot slotKey="史册" img="史册"
          caption="史冊" sub="歷代奏報/詔書" onClick={() => setActiveModal("history")} />
        <CommandSlot slotKey="拟诏" img="拟诏" badge={state.directives.length + (state.structured_directives?.length || 0)}
          caption="擬詔/結束回合" sub={(state.directives.length + (state.structured_directives?.length || 0)) ? `${state.directives.length + (state.structured_directives?.length || 0)} 道` : "本回合"}
          onClick={() => setActiveModal("edict")} />
      </div>

      <SituationDrawer
        open={situationDrawerOpen}
        issues={state.issues}
        closedIssues={state.closed_this_turn || []}
        maxDecreeIssues={state.max_decree_issues ?? 10}
        regions={(state.regions || []).filter((r) => (r.controlled_by ?? "ming") === "ming").map((r) => ({ id: r.id, name: r.name }))}
        ministers={state.ministers || []}
        presetTrees={state.preset_trees}
        onChanged={() => loadState()}
        onClose={() => setSituationDrawerOpen(false)}
      />

      <CourtDrawer
        state={state}
        ministers={ministers}
        ministerGroup={ministerGroup}
        selectedMinister={selectedMinister}
        open={drawerOpen}
        onGroupChange={setMinisterGroup}
        onClose={guardClose(() => setDrawerOpen(false))}
        onOpenChat={openChat}
        onRestoreMinister={restoreMinister}
        onUploadPortrait={uploadPortrait}
        courtChatHistory={courtChatHistory}
        courtChatInput={courtChatInput}
        courtChatBusy={courtChatBusy}
        courtChatError={courtChatError}
        courtChatBubbles={courtChatBubbles}
        courtChatPanelOpen={courtChatPanelOpen}
        courtChatLiveMessages={courtChatLiveMessages}
        courtChatDecision={courtChatDecision}
        courtChatSelectedMinisters={courtChatSelectedMinisters}
        courtChatStreamSpeed={courtChatStreamSpeed}
        onCourtChatSelectedMinistersChange={setCourtChatSelectedMinisters}
        onCourtChatInputChange={setCourtChatInput}
        onCourtChatStreamSpeedChange={updateCourtChatStreamSpeed}
        onSendCourtChat={sendCourtChat}
        onStopCourtChat={stopCourtChat}
        onSummarizeCourtChat={summarizeCourtChat}
        onRefreshCourtChat={refreshCourtChatWithError}
        onCloseCourtChatPanel={() => setCourtChatPanelOpen(false)}
        onChooseCourtChatDecision={chooseCourtChatDecision}
      />

      <HaremDrawer
        consorts={consorts}
        haremGroup={haremGroup}
        selectedMinister={selectedMinister}
        open={haremDrawerOpen}
        onGroupChange={setHaremGroup}
        onClose={guardClose(() => setHaremDrawerOpen(false))}
        onOpenChat={openChat}
        onUploadPortrait={uploadPortrait}
      />

      <ArmyDrawer
        armies={state.armies}
        armsStock={state.arms_stock}
        troopRates={state.troop_rates}
        open={armyDrawerOpen}
        selectedArmyId={selectedArmyId}
        onSelectArmy={setSelectedArmyId}
        onClose={guardClose(() => setArmyDrawerOpen(false))}
      />

      <RegionDrawer
        regions={state.regions}
        open={regionDrawerOpen}
        selectedRegionId={selectedRegionId}
        onSelectRegion={setSelectedRegionId}
        onClose={guardClose(() => setRegionDrawerOpen(false))}
      />

      {(() => {
        const selRegion = selectedRegionId ? state.regions.find((r) => r.id === selectedRegionId) : null;
        return selRegion ? (
          <RegionDetailModal region={selRegion} onClose={() => setSelectedRegionId("")} />
        ) : null;
      })()}

      <BuildingDrawer
        regions={state.regions}
        mapNodes={mapNodes}
        technologies={state.technologies}
        open={buildingDrawerOpen}
        onClose={guardClose(() => setBuildingDrawerOpen(false))}
      />

      <EconomyDrawer
        state={state}
        open={economyDrawerOpen}
        onClose={guardClose(() => setEconomyDrawerOpen(false))}
      />

      <AppointmentDrawer
        ministers={state.ministers}
        departments={state.departments || []}
        open={appointmentDrawerOpen}
        onOpenChat={openChat}
        onClose={guardClose(() => setAppointmentDrawerOpen(false))}
      />

      {mapIntelOpen && selectedNode ? (
        <section className="map-intel-panel overlay-panel" style={mapIntelStyle}>
          <button className="icon-button panel-close" aria-label="关闭地区详情" onClick={() => setMapIntelOpen(false)}>
            <X size={16} />
          </button>
          <NodeIntel node={selectedNode} />
        </section>
      ) : null}

      {activeModal === "state" ? (
        <FullscreenModal title="国势与奏报" subtitle={`${state.turn.year} 年 ${state.turn.period} 月`} bgClass="modal-bg-state" onClose={guardClose(() => setActiveModal("none"))}>
          <StateModal state={state} />
        </FullscreenModal>
      ) : null}

      {activeModal === "long_goals" ? (
        <LongGoalsModal onClose={guardClose(() => setActiveModal("none"))} />
      ) : null}

      {activeModal === "chat" && activeMinister ? (
        <FullscreenModal title={`召对：${activeMinister.name}`} subtitle={activeMinister.office} bgClass="modal-bg-chat" onClose={guardClose(() => setActiveModal("none"))}>
          <ChatModal
            minister={activeMinister}
            portraitPrefix={(state.consorts || []).some((c) => c.name === activeMinister.name) ? "consort_" : "minister_"}
            chat={chat}
            suggestions={suggestions}
            pendingDirectives={(state.directives || []).filter((d) => d.status === "pending")}
            pendingUserMessage={pendingUserMessage}
            streamingMinisterMessage={streamingMinisterMessage}
            chatNotice={chatNotice}
            composerHint={composerHint}
            input={input}
            busy={busy}
            error={error}
            secretOrders={secretOrders.filter((o) => o.minister_name === activeMinister.name && (o.status === "active" || o.status === "pending_review"))}
            onInput={setInput}
            onSend={sendChat}
            onHint={setComposerHint}
            onFavorite={() => toggleFavorite(activeMinister)}
            onConfirmDirective={confirmDirective}
            onRejectDirective={rejectDirective}
            onUndoLast={undoLastChat}
            onOpenEdict={() => setActiveModal("edict")}
            onArchive={() => archiveMinister(activeMinister)}
            onClose={guardClose(() => setActiveModal("none"))}
          />
        </FullscreenModal>
      ) : null}

      {activeModal === "edict" ? (
        <FullscreenModal title="诏书草案" subtitle="本月指令、拟诏与颁布" bgClass="modal-bg-edict" onClose={guardClose(() => setActiveModal("none"))}>
          <EdictModal
            state={state}
            ministers={state.ministers || []}
            directiveText={directiveText}
            editingDirectiveId={editingDirectiveId}
            editingDirectiveText={editingDirectiveText}
            decree={decree}
            report={report}
            busy={busy}
            error={error}
            structuredDirectiveTemplates={structuredDirectiveTemplates}
            onDirectiveTextChange={setDirectiveText}
            onEditingTextChange={setEditingDirectiveText}
            onCreateDirective={createDirective}
            onStartEdit={startEditDirective}
            onCancelEdit={cancelEditDirective}
            onSaveDirective={saveDirective}
            onDeleteDirective={deleteDirective}
            onWriteDecree={writeDecree}
            onRewriteDecree={rewriteDecree}
            onSaveDecree={saveDecree}
            onResetDecree={resetDecree}
            onIssueDecree={issueDecree}
            onConfirmDirective={confirmDirective}
            onRejectDirective={rejectDirective}
            onConfirmAllDirectives={confirmAllDirectives}
            onSaveStructuredDirective={saveStructuredDirective}
            onDeleteStructuredDirective={deleteStructuredDirective}
            onGoToCourtChat={() => { setActiveModal("none"); setDrawerOpen(true); }}
            onIssueCreated={() => loadState()}
          />
        </FullscreenModal>
      ) : null}

      {activeModal === "report" && (gazetteReport || report) ? (
        <ReportModal report={gazetteReport || report} onClose={guardClose(() => setActiveModal("none"))} />
      ) : null}

      {activeModal === "ending" && state.ending ? (
        <EndingModal ending={state.ending} onClose={() => { setEndingDismissed(true); setActiveModal("none"); }} />
      ) : null}

      {activeModal === "extraction" ? (
        <ExtractionModal onClose={guardClose(() => setActiveModal("none"))} />
      ) : null}

      {activeModal === "history" ? (
        <HistoryModal onClose={guardClose(() => setActiveModal("none"))} />
      ) : null}

      {activeModal === "menu" ? (
        <GameMenuModal
          onClose={guardClose(() => setActiveModal("none"))}
          onAfterLoad={() => {
            setActiveModal("none");
            window.location.reload();
          }}
          onExitToMenu={async () => {
            await exitToMenu();
            setActiveModal("none");
          }}
        />
      ) : null}

      {closedModal.length ? (
        <ClosedIssuesModal items={closedModal} onClose={() => setClosedModal([])} />
      ) : null}

      {activeModal === "secret_orders" ? (
        <SecretOrdersModal
          orders={secretOrders}
          onClose={() => setActiveModal("none")}
          onOpenMinister={(name) => {
            setActiveModal("chat");
            setSelectedMinister(name);
          }}
          onDelete={async (order) => {
            try {
              await api(`/api/secret_orders/${order.id}`, { method: "DELETE" });
              const { orders } = await api<{ orders: SecretOrder[] }>("/api/secret_orders");
              setSecretOrders(orders);
            } catch (e: any) {
              window.alert(e?.message || "删除密令失败");
            }
          }}
        />
      ) : null}

      {settling ? (
        <SettlementLock
          stage={settleStage}
          thinking={settleThinking}
          narrative={settleNarrative}
        />
      ) : null}

      {cheatOpen ? (
        <CheatConsole
          directive={cheatDirective}
          onCommit={setCheatDirective}
          onClose={() => setCheatOpen(false)}
        />
      ) : null}

      {pendingDecisions.length > 0 && !settling ? (
        <DecisionModal decisions={pendingDecisions} onResolve={submitDecisions} />
      ) : null}
    </main>
  );
}

const canAttendCourtChat = (minister: Minister) => {
  const office = (minister.office || "").trim();
  if (minister.status !== "active" || !office) return false;
  return !/(已故|罢居|罢闲|赋闲|致仕|养病|丁忧|归籍|在野)/.test(office);
};


// HITL 遇阻纠偏弹窗：逐个亲裁本回合纠偏点，全部选完一次提交续跑结算。
// 每个纠偏：标题 + 背景 + 2-3 预设选项（点选）+ 朱批输入框（可补自由旨意）。
function DecisionModal({
  decisions,
  onResolve,
}: {
  decisions: PendingDecision[];
  onResolve: (choices: { label?: string; hint?: string; note?: string }[]) => void;
}) {
  const [cursor, setCursor] = React.useState(0);
  const [picks, setPicks] = React.useState<{ label?: string; hint?: string; note?: string }[]>(
    () => decisions.map(() => ({}))
  );
  const total = decisions.length;
  const cur = decisions[cursor];
  const pick = picks[cursor] || {};

  const setOption = (label: string, hint: string) =>
    setPicks((p) => p.map((x, i) => (i === cursor ? { ...x, label, hint } : x)));
  const setNote = (note: string) =>
    setPicks((p) => p.map((x, i) => (i === cursor ? { ...x, note } : x)));

  const decided = !!(pick.label || (pick.note || "").trim());
  const last = cursor >= total - 1;

  const next = () => {
    if (!decided) return;
    if (last) onResolve(picks);
    else setCursor((c) => c + 1);
  };

  return (
    <div className="decision-modal" role="dialog" aria-modal="true" aria-label="月末遇阻纠偏">
      <div className="decision-window">
        <div className="decision-head">
          <span className="decision-kicker">遇阻纠偏 · {cursor + 1}/{total}</span>
          <h2 className="decision-title">{cur.title}</h2>
        </div>
        {cur.context ? <p className="decision-context">{cur.context}</p> : null}
        <div className="decision-options">
          {cur.options.map((o, i) => (
            <button
              key={i}
              className={"decision-option" + (pick.label === o.label ? " is-picked" : "")}
              onClick={() => setOption(o.label, o.hint)}
            >
              <span className="decision-option-label">{o.label}</span>
              {o.hint ? <span className="decision-option-hint">{o.hint}</span> : null}
            </button>
          ))}
        </div>
        <textarea
          className="decision-note"
          placeholder="朱批（可选）：另有旨意可亲笔补写，将与所选一并定夺。"
          value={pick.note || ""}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="decision-actions">
          <span className="decision-hint-line">
            {decided ? "" : "请择一选项或亲笔朱批，方可下一步。"}
          </span>
          <button className="decision-confirm" disabled={!decided} onClick={next}>
            {last ? "御笔亲断，续推时局" : "下一桩抉择"}
          </button>
        </div>
      </div>
    </div>
  );
}


// 作弊控制台：terminal UI。强制结算唯一入口（Ctrl+~ 唤出）。输入的指令暂存于
// cheatDirective，下次颁诏时随结算穿入 extractor 当既成事实落库。
function CheatConsole({
  directive,
  onCommit,
  onClose,
}: {
  directive: string;
  onCommit: (text: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = React.useState("");
  const [history, setHistory] = React.useState<string[]>([]);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const bodyRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    inputRef.current?.focus();
  }, []);
  React.useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [history]);

  const submit = () => {
    const text = draft.trim();
    if (!text) return;
    onCommit(text);
    setHistory((h) => [...h, `> ${text}`, "  已挂载强制结算项，下次颁诏随结算生效（一次性）。"]);
    setDraft("");
  };

  const clearMounted = () => {
    onCommit("");
    setHistory((h) => [...h, "  已清空强制结算项。"]);
  };

  return (
    <div className="cheat-console" role="dialog" aria-label="天命控制台" onClick={onClose}>
      <div className="cheat-console-window" onClick={(e) => e.stopPropagation()}>
        <div className="cheat-console-titlebar">
          <span>tianming@ming-salvage:~$ 天命控制台</span>
          <button className="cheat-console-x" onClick={onClose} aria-label="关闭">×</button>
        </div>
        <div className="cheat-console-body" ref={bodyRef}>
          <div className="cheat-console-line cheat-console-dim">
            强制结算控制台。输入的指令将在下次颁诏时作为「既成事实」穿入结算，无视合理性与史实。
          </div>
          <div className="cheat-console-line cheat-console-dim">
            Enter 提交 · Shift+Enter 换行 · Ctrl+~ 关闭
          </div>
          {directive ? (
            <div className="cheat-console-line cheat-console-armed">
              ● 当前已挂载：{directive}
            </div>
          ) : (
            <div className="cheat-console-line cheat-console-dim">○ 当前无挂载项</div>
          )}
          {history.map((line, i) => (
            <div className="cheat-console-line" key={i}>{line}</div>
          ))}
        </div>
        <div className="cheat-console-prompt">
          <span className="cheat-console-caret">&gt;</span>
          <textarea
            ref={inputRef}
            className="cheat-console-input"
            value={draft}
            rows={1}
            placeholder="例：国库增至九千万两，后金军覆灭，皇太极暴毙"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing || e.keyCode === 229) return;
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
        </div>
        <div className="cheat-console-actions">
          <button className="cheat-console-btn" onClick={submit}>挂载</button>
          <button className="cheat-console-btn cheat-console-btn-ghost" onClick={clearMounted}>清空挂载</button>
        </div>
      </div>
    </div>
  );
}

function SettlementLock({
  stage,
  thinking,
  narrative,
}: {
  stage: string;
  thinking: string;
  narrative: string;
}) {
  const thinkRef = React.useRef<HTMLDivElement>(null);
  const narrRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const block = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("keydown", block, true);
    return () => window.removeEventListener("keydown", block, true);
  }, []);
  // 流式内容到达时自动滚到底
  React.useEffect(() => {
    if (thinkRef.current) thinkRef.current.scrollTop = thinkRef.current.scrollHeight;
  }, [thinking]);
  React.useEffect(() => {
    if (narrRef.current) narrRef.current.scrollTop = narrRef.current.scrollHeight;
  }, [narrative]);
  return (
    <div className="settlement-lock" role="alertdialog" aria-modal="true" aria-label="月末结算">
      <div className="settlement-lock-card">
        <Loader2 className="settlement-spin" size={28} />
        <h2>月末结算中</h2>
        <p>{stage === "数值推演结算" ? "档房核账中，钱粮、地方、军务落账，请稍候。" : stage ? `当前：${stage}` : "朝廷推演钱粮、地方、军务，请勿操作。"}</p>
        {thinking && (
          <div className="settlement-stream-block">
            <div className="settlement-stream-label">邸报房推敲</div>
            <div className="settlement-stream-text settlement-thinking" ref={thinkRef}>
              {thinking}
            </div>
          </div>
        )}
        {narrative && (
          <div className="settlement-stream-block">
            <div className="settlement-stream-label">月末奏章</div>
            <div className="settlement-stream-text settlement-narrative" ref={narrRef}>
              {narrative}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
