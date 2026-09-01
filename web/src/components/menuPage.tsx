import React from "react";
import { Loader2, Trash2 } from "lucide-react";
import { api, apiUrl, normalizeApiError } from "../api";
import type { MenuCampaign, MenuStatus } from "../types";
import { ScenarioManagerModal } from "./scenarioManager";

type LauncherLogInfo = {
  data_dir: string;
  log_path: string;
  exists: boolean;
  content: string;
};

export function MenuPage({
  status,
  onRefresh,
  onEnterGame,
  error,
  setError,
}: {
  status: MenuStatus | null;
  onRefresh: () => Promise<MenuStatus>;
  onEnterGame: () => Promise<void>;
  error: string;
  setError: (msg: string) => void;
}) {
  const [busy, setBusy] = React.useState<string>("");
  const [showApiForm, setShowApiForm] = React.useState(false);
  const [showSaveList, setShowSaveList] = React.useState(false);
  const [showGameSettings, setShowGameSettings] = React.useState(false);
  const [showDebugTools, setShowDebugTools] = React.useState(false);
  const [showScenarios, setShowScenarios] = React.useState(false);

  const guard = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy("");
    }
  };

  const onNewGame = () =>
    guard("新游戏中...", async () => {
      if (status?.has_main_db && !window.confirm("将覆盖当前主进度，是否继续？建议先在游戏中保存为存档。")) return;
      await api("/api/menu/new_game", { method: "POST" });
      await onEnterGame();
    });

  const onContinue = () =>
    guard("载入上次进度...", async () => {
      await api("/api/menu/continue", { method: "POST" });
      await onEnterGame();
    });

  const onLoadSave = (name: string) =>
    guard(`载入「${name}」...`, async () => {
      await api(`/api/menu/load_save/${encodeURIComponent(name)}`, { method: "POST" });
      await onEnterGame();
    });

  const hasKey = !!status?.has_api_key;
  const hasMainDb = !!status?.has_main_db;
  const saves = status?.saves || [];
  const campaigns = status?.campaigns || [];

  return (
    <div className="menu-screen">
      <div className="menu-poster">
        <img src="/menu-start.webp" alt="明末：力挽狂澜" />
      </div>

      <h1 className="menu-title">明末：力挽狂澜</h1>

      <div className="menu-panel">
        <p className="menu-subtitle">崇祯元年正月 · 召大臣议天下事</p>

        {!hasKey && (
          <div className="menu-notice">尚未配置 API 接口。请先「设置 API」。</div>
        )}
        {error && <div className="menu-error">{error}</div>}

        <div className="menu-buttons">
          <button className="menu-btn primary" disabled={!hasKey || !!busy} onClick={onNewGame}>
            开始新游戏
          </button>
          <button className="menu-btn" disabled={!hasKey || !hasMainDb || !!busy} onClick={onContinue} title={hasMainDb ? "" : "无上次进度"}>
            继续
          </button>
          <button className="menu-btn" disabled={!hasKey || !!busy || !saves.length} onClick={() => setShowSaveList(true)} title={saves.length ? "" : "暂无存档"}>
            加载存档 {saves.length ? `(${saves.length})` : ""}
          </button>
          <button className="menu-btn" disabled={!!busy} onClick={() => setShowApiForm(true)}>
            设置 API {hasKey ? "" : "（必需）"}
          </button>
          <button className="menu-btn" disabled={!!busy} onClick={() => setShowGameSettings(true)}>
            游戏设置
          </button>
          <button className="menu-btn" disabled={!!busy} onClick={() => setShowScenarios(true)}>
            自定义剧本
          </button>
          <button className="menu-btn" disabled={!!busy} onClick={() => setShowDebugTools(true)}>
            调试
          </button>
        </div>

        {busy && <div className="menu-busy">{busy}</div>}
        {hasKey && status?.llm && (
          <div className="menu-llm-info">
            当前接口：{status.llm.base_url} · {status.llm.model}
          </div>
        )}
        <div className="menu-llm-info">
          当前剧本：{status?.active_scenario?.name ?? "默认（崇祯元年）"}
        </div>
      </div>

      {showApiForm && (
        <ApiSettingsModal
          initial={status?.llm}
          onClose={() => setShowApiForm(false)}
          onSaved={async () => {
            setShowApiForm(false);
            await onRefresh();
          }}
        />
      )}

      {showSaveList && (
        <SaveListModal
          campaigns={campaigns}
          onClose={() => setShowSaveList(false)}
          onLoad={async (name) => {
            setShowSaveList(false);
            await onLoadSave(name);
          }}
          onDelete={async (name) => {
            await api(`/api/menu/saves/${encodeURIComponent(name)}`, { method: "DELETE" });
            await onRefresh();
          }}
        />
      )}

      {showGameSettings && (
        <GameSettingsModal
          initial={status?.game_settings}
          onClose={() => setShowGameSettings(false)}
          onSaved={async () => {
            setShowGameSettings(false);
            await onRefresh();
          }}
        />
      )}

      {showDebugTools && (
        <DebugToolsModal onClose={() => setShowDebugTools(false)} />
      )}

      {showScenarios && (
        <ScenarioManagerModal
          onClose={() => setShowScenarios(false)}
          onChanged={async () => {
            await onRefresh();
          }}
        />
      )}
    </div>
  );
}

function DebugToolsModal({ onClose }: { onClose: () => void }) {
  const [info, setInfo] = React.useState<LauncherLogInfo | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");

  const loadLog = React.useCallback(async () => {
    setBusy(true);
    setErr("");
    try {
      const payload = window.pywebview?.api?.get_launcher_log
        ? await window.pywebview.api.get_launcher_log()
        : await api<LauncherLogInfo>("/api/menu/debug/launcher_log");
      setInfo(payload);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  React.useEffect(() => {
    void loadLog();
  }, [loadLog]);

  const openDataDir = async () => {
    setBusy(true);
    setErr("");
    try {
      if (window.pywebview?.api?.open_data_dir) {
        await window.pywebview.api.open_data_dir();
      } else {
        await api("/api/menu/debug/open_data_dir", { method: "POST" });
      }
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="menu-modal-bg" onClick={onClose}>
      <div className="menu-modal menu-debug-modal" onClick={(e) => e.stopPropagation()}>
        <h2>调试</h2>
        <p className="menu-hint">存档目录：{info?.data_dir || "读取中..."}</p>
        <p className="menu-hint">日志文件：{info?.log_path || "读取中..."}</p>
        {err && <div className="menu-error">{err}</div>}
        <div className="menu-modal-actions menu-debug-actions">
          <button onClick={openDataDir} disabled={busy}>打开存档目录</button>
          <button onClick={loadLog} disabled={busy}>{busy ? "读取中..." : "刷新日志"}</button>
        </div>
        <pre className="menu-launcher-log">
          {info?.exists
            ? info.content || "launcher.log 为空。"
            : "尚未找到 launcher.log。打包启动器运行后会写入此文件。"}
        </pre>
        <div className="menu-modal-actions">
          <button className="primary" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}

export function GameSettingsModal({
  initial,
  onClose,
  onSaved,
}: {
  initial?: {
    hitl_min_decisions: number;
    court_chat_debate_rounds?: number;
    court_chat_stream_speed?: number;
    max_decree_issues?: number;
    issue_log_limit?: number;
    secret_order_person_limit?: number;
    secret_order_total_limit?: number;
    character_limit?: number;
    minister_temperature?: number;
    minister_top_p?: number;
    simulator_temperature?: number;
    simulator_top_p?: number;
    extractor_temperature?: number;
    extractor_top_p?: number;
  };
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [minDecisions, setMinDecisions] = React.useState<number>(
    initial?.hitl_min_decisions ?? 1
  );
  const [courtChatDebateRounds, setCourtChatDebateRounds] = React.useState<number>(
    initial?.court_chat_debate_rounds ?? 3
  );
  const [courtChatStreamSpeed, setCourtChatStreamSpeed] = React.useState<number>(
    initial?.court_chat_stream_speed ?? 3
  );
  const [maxDecreeIssues, setMaxDecreeIssues] = React.useState<number>(
    initial?.max_decree_issues ?? 10
  );
  const [issueLogLimit, setIssueLogLimit] = React.useState<number>(
    initial?.issue_log_limit ?? 6
  );
  const [secretOrderPersonLimit, setSecretOrderPersonLimit] = React.useState<number>(
    initial?.secret_order_person_limit ?? 1
  );
  const [secretOrderTotalLimit, setSecretOrderTotalLimit] = React.useState<number>(
    initial?.secret_order_total_limit ?? 5
  );
  const [characterLimit, setCharacterLimit] = React.useState<number>(
    initial?.character_limit ?? 120
  );
  const [ministerTemperature, setMinisterTemperature] = React.useState<number>(
    initial?.minister_temperature ?? 0.6
  );
  const [ministerTopP, setMinisterTopP] = React.useState<number>(
    initial?.minister_top_p ?? 0.9
  );
  const [simulatorTemperature, setSimulatorTemperature] = React.useState<number>(
    initial?.simulator_temperature ?? 0.5
  );
  const [simulatorTopP, setSimulatorTopP] = React.useState<number>(
    initial?.simulator_top_p ?? 0.5
  );
  const [extractorTemperature, setExtractorTemperature] = React.useState<number>(
    initial?.extractor_temperature ?? 0.1
  );
  const [extractorTopP, setExtractorTopP] = React.useState<number>(
    initial?.extractor_top_p ?? 0.1
  );
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");

  const onSave = async () => {
    setBusy(true);
    setErr("");
    try {
      await api("/api/menu/game_settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hitl_min_decisions: minDecisions,
          court_chat_debate_rounds: courtChatDebateRounds,
          court_chat_stream_speed: courtChatStreamSpeed,
          max_decree_issues: maxDecreeIssues,
          issue_log_limit: issueLogLimit,
          secret_order_person_limit: secretOrderPersonLimit,
          secret_order_total_limit: secretOrderTotalLimit,
          character_limit: characterLimit,
          minister_temperature: ministerTemperature,
          minister_top_p: ministerTopP,
          simulator_temperature: simulatorTemperature,
          simulator_top_p: simulatorTopP,
          extractor_temperature: extractorTemperature,
          extractor_top_p: extractorTopP,
        }),
      });
      await onSaved();
    } catch (e: any) {
      setErr(e?.message || String(e));
      setBusy(false);
    }
  };

  return (
    <div className="menu-modal-bg" onClick={onClose}>
      <div className="menu-modal" onClick={(e) => e.stopPropagation()}>
        <h2>游戏设置</h2>
        {err && <div className="menu-error">{err}</div>}
        <label>
          每回合最多遇阻纠偏数{" "}
          <small className="menu-hint">
            （月末推演最多弹几个承办遇阻后的亲裁纠偏。0=关闭遇阻纠偏；改动下一回合生效。）
          </small>
          <select
            value={minDecisions}
            onChange={(e) => setMinDecisions(Number(e.target.value))}
          >
            <option value={0}>0 · 关闭遇阻纠偏</option>
            <option value={1}>1 · 每回合最多 1 个</option>
            <option value={2}>2 · 每回合最多 2 个</option>
            <option value={3}>3 · 每回合最多 3 个</option>
            <option value={4}>4 · 每回合最多 4 个</option>
            <option value={5}>5 · 每回合最多 5 个</option>
          </select>
        </label>
        <label>
          朝会交锋轮数{" "}
          <small className="menu-hint">
            （群臣未形成结论前，最多驱动几轮继续廷辩。默认 3，数字越高越能吵，耗时和 token 也越多。）
          </small>
          <select
            value={courtChatDebateRounds}
            onChange={(e) => setCourtChatDebateRounds(Number(e.target.value))}
          >
            <option value={1}>1 · 简短交锋</option>
            <option value={2}>2 · 适中交锋</option>
            <option value={3}>3 · 默认交锋</option>
            <option value={4}>4 · 更激烈</option>
            <option value={5}>5 · 长朝会</option>
            <option value={6}>6 · 很能吵</option>
            <option value={7}>7 · 持续廷辩</option>
            <option value={8}>8 · 极长廷辩</option>
          </select>
        </label>
        <label>
          朝会流式速度{" "}
          <small className="menu-hint">
            （控制朝会群臣文字逐段显示的默认速度。1=慢，3=默认，5=最快；朝会面板内可临时再调。）
          </small>
          <select
            value={courtChatStreamSpeed}
            onChange={(e) => setCourtChatStreamSpeed(Number(e.target.value))}
          >
            <option value={1}>1 · 慢</option>
            <option value={2}>2 · 稍慢</option>
            <option value={3}>3 · 默认</option>
            <option value={4}>4 · 快</option>
            <option value={5}>5 · 最快</option>
          </select>
        </label>
        <label>
          decree 局势上限{" "}
          <small className="menu-hint">
            （皇帝手动新建与大模型从诏书抽取的 decree 来源局势，共用此 active 总上限。默认 10。
            <b>调高会让月末推演多带局势进盘面叙述，token 消耗随之增加。</b>）
          </small>
          <select
            value={maxDecreeIssues}
            onChange={(e) => setMaxDecreeIssues(Number(e.target.value))}
          >
            <option value={10}>10 · 默认</option>
            <option value={15}>15 · 略增（token ↑）</option>
            <option value={20}>20 · 较多（token ↑↑）</option>
            <option value={25}>25 · 很多（token ↑↑↑）</option>
            <option value={30}>30 · 上限（token 大幅增加）</option>
          </select>
        </label>
        <label>
          密令个人上限{" "}
          <small className="menu-hint">
            （同一承办人同时进行中的 active 密令数量。默认 1；调高会让单个大臣背更多暗线。）
          </small>
          <select
            value={secretOrderPersonLimit}
            onChange={(e) => setSecretOrderPersonLimit(Number(e.target.value))}
          >
            <option value={1}>1 · 默认</option>
            <option value={2}>2 · 较忙</option>
            <option value={3}>3 · 多线承办</option>
            <option value={5}>5 · 重臣密办</option>
            <option value={10}>10 · 上限</option>
          </select>
        </label>
        <label>
          密令总上限{" "}
          <small className="menu-hint">
            （全朝同时进行中的 active 密令总数。默认 5；调高会增加月末推演携带的密令盘面。）
          </small>
          <select
            value={secretOrderTotalLimit}
            onChange={(e) => setSecretOrderTotalLimit(Number(e.target.value))}
          >
            <option value={5}>5 · 默认</option>
            <option value={8}>8 · 略增</option>
            <option value={10}>10 · 较多</option>
            <option value={15}>15 · 很多</option>
            <option value={20}>20 · 密网</option>
            <option value={50}>50 · 上限</option>
          </select>
        </label>
        <label>
          朝臣人物上限{" "}
          <small className="menu-hint">
            （本局未归档朝臣建档上限，后宫不计入。朝臣越多，大臣名册、召对背景与月末推演上下文越长，<b>token 消耗会增加。</b>）
          </small>
          <select
            value={characterLimit}
            onChange={(e) => setCharacterLimit(Number(e.target.value))}
          >
            <option value={80}>80 · 节省 token</option>
            <option value={120}>120 · 默认</option>
            <option value={160}>160 · 较多（token ↑）</option>
            <option value={220}>220 · 很多（token ↑↑）</option>
            <option value={300}>300 · 上限（token 大幅增加）</option>
          </select>
        </label>
        <label>
          Agent 采样参数{" "}
          <small className="menu-hint">
            （temperature / top_p，范围 0-1。默认沿用代码原值：大臣 0.6/0.9，推演 0.5/0.5，结算 0.1/0.1。）
          </small>
          <div className="agent-sampling-grid">
            <span>大臣</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={ministerTemperature}
              onChange={(e) => setMinisterTemperature(Number(e.target.value))}
              aria-label="大臣 temperature"
            />
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={ministerTopP}
              onChange={(e) => setMinisterTopP(Number(e.target.value))}
              aria-label="大臣 top_p"
            />
            <span>推演</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={simulatorTemperature}
              onChange={(e) => setSimulatorTemperature(Number(e.target.value))}
              aria-label="推演 temperature"
            />
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={simulatorTopP}
              onChange={(e) => setSimulatorTopP(Number(e.target.value))}
              aria-label="推演 top_p"
            />
            <span>结算</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={extractorTemperature}
              onChange={(e) => setExtractorTemperature(Number(e.target.value))}
              aria-label="结算 temperature"
            />
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={extractorTopP}
              onChange={(e) => setExtractorTopP(Number(e.target.value))}
              aria-label="结算 top_p"
            />
          </div>
        </label>
        <label>
          局势日志注入条数{" "}
          <small className="menu-hint">
            （每条 active 局势最多带最近几条推进日志进月末推演。0=不带日志；默认 6。）
          </small>
          <select
            value={issueLogLimit}
            onChange={(e) => setIssueLogLimit(Number(e.target.value))}
          >
            <option value={0}>0 · 不带推进日志</option>
            <option value={3}>3 · 最近 3 条</option>
            <option value={6}>6 · 默认</option>
            <option value={10}>10 · 较完整</option>
            <option value={20}>20 · 长历史</option>
            <option value={50}>50 · 上限</option>
          </select>
        </label>
        <div className="menu-modal-actions">
          <button onClick={onClose} disabled={busy}>取消</button>
          <button className="primary" onClick={onSave} disabled={busy}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function ApiSettingsModal({
  initial,
  onClose,
  onSaved,
}: {
  initial?: {
    base_url: string;
    model: string;
    has_api_key: boolean;
    max_tokens?: number;
    timeout_seconds?: number;
    connect_timeout_seconds?: number;
    read_timeout_seconds?: number;
    thinking_level?: string;
    advanced_model?: string;
    advanced_base_url?: string;
    has_advanced_api_key?: boolean;
    advanced_thinking_level?: string;
  };
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [baseUrl, setBaseUrl] = React.useState(initial?.base_url || "https://api.deepseek.com");
  const [model, setModel] = React.useState(initial?.model || "deepseek-chat");
  const [advancedModel, setAdvancedModel] = React.useState(initial?.advanced_model || "");
  const [advancedBaseUrl, setAdvancedBaseUrl] = React.useState(initial?.advanced_base_url || "");
  const [advancedApiKey, setAdvancedApiKey] = React.useState("");
  const [advancedThinkingLevel, setAdvancedThinkingLevel] = React.useState(initial?.advanced_thinking_level || "");
  const [apiKey, setApiKey] = React.useState("");
  const [maxTokens, setMaxTokens] = React.useState(String(initial?.max_tokens || 8000));
  const [timeoutSeconds, setTimeoutSeconds] = React.useState(String(initial?.timeout_seconds || 180));
  const [connectTimeoutSeconds, setConnectTimeoutSeconds] = React.useState(String(initial?.connect_timeout_seconds || 60));
  const [readTimeoutSeconds, setReadTimeoutSeconds] = React.useState(String(initial?.read_timeout_seconds || 120));
  const [thinkingLevel, setThinkingLevel] = React.useState(initial?.thinking_level || "");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");

  const onSave = async () => {
    setBusy(true);
    setErr("");
    try {
      const response = await fetch(apiUrl("/api/menu/llm"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: baseUrl.trim(),
          model: model.trim(),
          api_key: apiKey.trim(),
          max_tokens: parseInt(maxTokens) || 8000,
          timeout_seconds: parseFloat(timeoutSeconds) || 180,
          connect_timeout_seconds: parseFloat(connectTimeoutSeconds) || 60,
          read_timeout_seconds: parseFloat(readTimeoutSeconds) || 120,
          thinking_level: thinkingLevel.trim(),
          advanced_model: advancedModel.trim(),
          advanced_base_url: advancedBaseUrl.trim(),
          advanced_api_key: advancedApiKey.trim(),
          advanced_thinking_level: advancedThinkingLevel.trim(),
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: response.statusText }));
        const detail = normalizeApiError(payload, response.statusText);
        setErr(`code: ${detail.code || "unknown"}\nmessage: ${detail.message || response.statusText}`);
        return;
      }
      await onSaved();
    } catch (e: any) {
      setErr(`code: request_failed\nmessage: ${e?.message || String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="menu-modal-bg" onClick={onClose}>
      <div className="menu-modal" onClick={(e) => e.stopPropagation()}>
        <h2>设置 API</h2>
        <p className="menu-hint">推荐 DeepSeek（中文好、价格便宜）。配置写入本地，不上传。</p>
        <label>
          Base URL
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.deepseek.com" />
        </label>
        <label>
          Model
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="deepseek-chat" />
        </label>
        <label>
          Thinking Level <small className="menu-hint">（空=默认，请填写你的模型支持的值。）</small>
          <input value={thinkingLevel} onChange={(e) => setThinkingLevel(e.target.value)} placeholder="默认" />
        </label>
        <label>
          Advanced Model <small className="menu-hint">（推演 + 打分专用；留空 fallback）</small>
          <input value={advancedModel} onChange={(e) => setAdvancedModel(e.target.value)} placeholder="deepseek-reasoner / gpt-5" />
        </label>
        <label>
          Advanced Base URL <small className="menu-hint">（advanced 专用网关；留空复用主 Base URL）</small>
          <input value={advancedBaseUrl} onChange={(e) => setAdvancedBaseUrl(e.target.value)} placeholder="https://other-gateway/v1" />
        </label>
        <label>
          Advanced API Key{" "}
          <small className="menu-hint">{initial?.has_advanced_api_key ? "(已配置；留空保留)" : "(留空=复用主 API Key)"}</small>
          <input type="password" value={advancedApiKey} onChange={(e) => setAdvancedApiKey(e.target.value)} placeholder={initial?.has_advanced_api_key ? "(已配置；如需更换请重新填写)" : "留空=复用主 Key"} />
        </label>
        <label>
          Advanced Thinking Level <small className="menu-hint">（空=默认，请填写你的模型支持的值。）</small>
          <input value={advancedThinkingLevel} onChange={(e) => setAdvancedThinkingLevel(e.target.value)} placeholder="默认" />
        </label>
        <label>
          Max Tokens
          <input type="number" min={256} max={65536} value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} placeholder="8000" />
        </label>
        <label>
          Timeout Seconds（总超时）
          <input type="number" min={10} max={900} value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(e.target.value)} placeholder="180" />
        </label>
        <label>
          Connect Timeout（建连超时）
          <input type="number" min={1} max={300} value={connectTimeoutSeconds} onChange={(e) => setConnectTimeoutSeconds(e.target.value)} placeholder="60" />
        </label>
        <label>
          Read Timeout（流式 chunk 间隔上限）
          <input type="number" min={5} max={600} value={readTimeoutSeconds} onChange={(e) => setReadTimeoutSeconds(e.target.value)} placeholder="120" />
        </label>
        <label>
          API Key
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={initial?.has_api_key ? "(已配置；如需更换请重新填写)" : "sk-..."} />
        </label>
        {err && <div className="menu-error">{err}</div>}
        <div className="menu-modal-actions">
          <button onClick={onClose} disabled={busy}>取消</button>
          <button className="primary" onClick={onSave} disabled={busy || !baseUrl.trim() || !model.trim() || (!apiKey.trim() && !initial?.has_api_key)}>
            {busy ? "保存中..." : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function SaveListModal({
  campaigns,
  onClose,
  onLoad,
  onDelete,
}: {
  campaigns: MenuCampaign[];
  onClose: () => void;
  onLoad: (name: string) => Promise<void>;
  onDelete: (name: string) => Promise<void>;
}) {
  const hasAny = campaigns.some((c) => c.saves.length);
  const [delBusy, setDelBusy] = React.useState("");
  const [delErr, setDelErr] = React.useState("");
  const handleDelete = async (name: string, label?: string) => {
    if (!window.confirm(`删除存档「${label || name}」？此操作不可撤销。`)) return;
    setDelBusy(name);
    setDelErr("");
    try {
      await onDelete(name);
    } catch (e) {
      setDelErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDelBusy("");
    }
  };
  return (
    <div className="menu-modal-bg" onClick={onClose}>
      <div className="menu-modal menu-save-modal" onClick={(e) => e.stopPropagation()}>
        <h2>加载存档</h2>
        {delErr ? <div className="menu-error">{delErr}</div> : null}
        {hasAny ? (
          <div className="menu-campaign-list">
            {campaigns.map((c) => (
              <div key={c.campaign_id || "__manual__"} className="menu-campaign">
                <div className="menu-campaign-head">
                  <span>{c.kind === "manual" ? "手动存档" : `战局 ${c.campaign_id.slice(0, 6)}`}</span>
                  {c.current ? <span className="menu-campaign-badge">本局</span> : null}
                </div>
                <ul className="menu-save-list">
                  {c.saves.map((s) => (
                    <li key={s.name} className="menu-save-row">
                      <button className="menu-save-load" onClick={() => onLoad(s.name)}>
                        <span className="save-name">{s.label || s.name}</span>
                        <span className="save-meta">{new Date(s.mtime * 1000).toLocaleString("zh-CN")}</span>
                      </button>
                      <button
                        className="menu-save-del"
                        title="删除存档"
                        disabled={delBusy === s.name}
                        onClick={() => handleDelete(s.name, s.label)}
                      >
                        {delBusy === s.name ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <p className="menu-empty">暂无存档。</p>
        )}
        <div className="menu-modal-actions">
          <button onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}
