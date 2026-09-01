import React from "react";
import { createPortal } from "react-dom";
import { Check, Crown, Info, Landmark, MapPinned, MessageSquareText, RotateCcw, ScrollText, Star, Swords, X } from "lucide-react";
import { MinisterPortrait, PortraitUploadButton, RightDrawer, cacheBust, courtSlots, loadCourtPos, saveCourtPos, snapToSlot } from "./hud";
import { formatMoney, formatSignedMoney, regionMonthlyTax } from "../format";
import type { Army, ArmsStockItem, Building, CourtChatMessage, Department, GameState, Issue, MapNode, Minister, Region, Technology } from "../types";

const canAttendCourtChat = (minister: Minister) => {
  if (minister.archived) return false;
  const office = (minister.office || "").trim();
  if (minister.status !== "active" || !office) return false;
  return !/(已故|罢居|罢闲|赋闲|致仕|养病|丁忧|归籍|在野)/.test(office);
};

function CourtChatAvatar({ message }: { message: CourtChatMessage }) {
  if (message.role === "emperor") {
    return (
      <div className="court-chat-avatar emperor-avatar">
        <Crown size={18} />
      </div>
    );
  }
  if (message.role === "conclusion") {
    return <div className="court-chat-avatar conclusion-avatar">议</div>;
  }
  const name = message.speaker || "臣";
  return (
    <div className="court-chat-avatar">
      <img
        src={`/portraits/minister_${encodeURIComponent(name)}.png`}
        alt={name}
        onError={(e) => {
          e.currentTarget.style.display = "none";
          e.currentTarget.parentElement?.setAttribute("data-fallback", name.slice(0, 1) || "臣");
        }}
      />
    </div>
  );
}

export function MinisterCardList({
  list,
  portraitPrefix,
  selectedMinister,
  emptyNote,
  onOpenChat,
  onRestoreMinister,
  onUploadPortrait,
  courtMode = false,
  courtBubbles = {},
  selectionMode = false,
  selectedNames = [],
  onToggleSelect,
  isSelectable,
  draggableOrder = false,
  onReorder,
}: {
  list: Minister[];
  portraitPrefix: string;
  selectedMinister: string;
  emptyNote: string;
  onOpenChat: (minister: Minister) => void;
  onRestoreMinister?: (minister: Minister) => void;
  onUploadPortrait?: (ministerName: string, file: File) => Promise<void>;
  courtMode?: boolean;
  courtBubbles?: Record<string, string>;
  selectionMode?: boolean;
  selectedNames?: string[];
  onToggleSelect?: (minister: Minister) => void;
  isSelectable?: (minister: Minister) => boolean;
  draggableOrder?: boolean;
  onReorder?: (fromName: string, toName: string) => void;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [positions, setPositions] = React.useState<Record<string, { px: number; py: number }>>({});
  const savedPosRef = React.useRef<Record<string, { px: number; py: number }> | null>(null);
  const dragging = React.useRef<{ name: string; pointerId: number; startMX: number; startMY: number; startPX: number; startPY: number } | null>(null);
  const orderDragging = React.useRef<string | null>(null);
  const didDrag = React.useRef(false);
  const suppressNextClick = React.useRef(false);

  // 固定职位 → 固定槽位（由 office 文字推导：office 逗号分项里命中即占该槽）
  const FIXED_SLOTS: { role: string; side: "left" | "right"; slot: number }[] = [
    { role: "首辅",    side: "left",  slot: 0 },
    { role: "次辅",    side: "right", slot: 0 },
    { role: "吏部尚书", side: "left",  slot: 1 },
    { role: "户部尚书", side: "right", slot: 1 },
    { role: "礼部尚书", side: "left",  slot: 2 },
    { role: "兵部尚书", side: "right", slot: 2 },
    { role: "刑部尚书", side: "left",  slot: 3 },
    { role: "工部尚书", side: "right", slot: 3 },
  ];

  // 从 office 字符串推导固定席位：逗号切分，任一分项精确等于某固定职名即占该槽。
  // 南京XX尚书是留都缺，不占京职槽——精确匹配自然排除（分项是「南京兵部尚书」≠「兵部尚书」）。
  function roleFromOffice(office: string): string {
    const parts = (office || "").split(",").map((s) => s.trim());
    const fs = FIXED_SLOTS.find((f) => parts.includes(f.role));
    return fs ? fs.role : "";
  }

  function fixedSlotFor(role: string): { px: number; py: number } | null {
    if (!role) return null;
    const allSlots = courtSlots();
    const fs = FIXED_SLOTS.find((f) => f.role === role);
    if (!fs) return null;
    const s = allSlots.find((sl) => sl.side === fs.side && sl.slot === fs.slot);
    return s ? { px: s.px, py: s.py } : null;
  }

  // 拖动覆盖坐标只加载一次。list 变化只重排，不重 fetch。
  const listKey = list.map((m) => m.name).join("|");
  React.useEffect(() => {
    let cancelled = false;
    const arrange = (saved: Record<string, { px: number; py: number }>) => {
      if (cancelled) return;
      const allSlots = courtSlots();
      const next: Record<string, { px: number; py: number }> = {};
      const usedSlots = new Set<string>();

      list.forEach((m) => {
        const role = roleFromOffice(m.office || "");
        const fixed = fixedSlotFor(role);
        if (fixed) {
          next[m.name] = fixed;
          const fs = FIXED_SLOTS.find((f) => f.role === role);
          if (fs) usedSlots.add(`${fs.side}:${fs.slot}`);
        }
      });

      list.forEach((m) => {
        if (next[m.name]) return;
        if (saved[m.name]) {
          const cur = saved[m.name];
          let best = allSlots.find((s) => !usedSlots.has(`${s.side}:${s.slot}`)) ?? allSlots[0];
          let bestD = Infinity;
          for (const s of allSlots) {
            if (usedSlots.has(`${s.side}:${s.slot}`)) continue;
            const d = Math.hypot(s.px - cur.px, s.py - cur.py);
            if (d < bestD) { bestD = d; best = s; }
          }
          usedSlots.add(`${best.side}:${best.slot}`);
          next[m.name] = { px: best.px, py: best.py };
        } else {
          const slot = allSlots.find((s) => !usedSlots.has(`${s.side}:${s.slot}`));
          if (slot) {
            usedSlots.add(`${slot.side}:${slot.slot}`);
            next[m.name] = { px: slot.px, py: slot.py };
          } else {
            next[m.name] = { px: 0.5, py: 0.532 };
          }
        }
      });
      setPositions(next);
    };

    if (savedPosRef.current !== null) {
      arrange(savedPosRef.current);
    } else {
      loadCourtPos().then((saved) => {
        savedPosRef.current = saved;
        arrange(saved);
      });
    }
    return () => { cancelled = true; };
  }, [listKey]);

  const finishCourtDrag = React.useCallback((shouldSnap: boolean) => {
    const dragName = dragging.current?.name;
    if (dragName && shouldSnap) {
      setPositions((prev) => {
        const cur = prev[dragName];
        if (!cur) return prev;
        const occupied = new Set<string>();
        const snapped = snapToSlot(cur.px, cur.py, occupied, "");
        const next = { ...prev, [dragName]: snapped };
        savedPosRef.current = next;
        saveCourtPos(next);
        return next;
      });
    } else if (savedPosRef.current) {
      saveCourtPos(savedPosRef.current);
    }
    dragging.current = null;
    if (shouldSnap) {
      suppressNextClick.current = true;
      window.setTimeout(() => {
        suppressNextClick.current = false;
        didDrag.current = false;
      }, 0);
    } else {
      didDrag.current = false;
    }
  }, []);

  const onCourtPointerDown = (e: React.PointerEvent<HTMLButtonElement>, name: string) => {
    if ((e.target as HTMLElement).closest(".portrait-upload-btn")) return;
    if (e.button !== 0) return;
    e.preventDefault();
    const pos = positions[name] || { px: 0.5, py: 0.8 };
    dragging.current = { name, pointerId: e.pointerId, startMX: e.clientX, startMY: e.clientY, startPX: pos.px, startPY: pos.py };
    didDrag.current = false;
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onCourtPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragging.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    const dx = e.clientX - drag.startMX;
    const dy = e.clientY - drag.startMY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) didDrag.current = true;
    const el = containerRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (!width || !height) return;
    const npx = Math.max(0, Math.min(1, drag.startPX + dx / width));
    const npy = Math.max(0, Math.min(1, drag.startPY + dy / height));
    setPositions((prev) => {
      const next = { ...prev, [drag.name]: { px: npx, py: npy } };
      savedPosRef.current = next;
      return next;
    });
  };

  const onCourtPointerEnd = (e: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragging.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch {}
    finishCourtDrag(didDrag.current);
  };

  React.useEffect(() => {
    const cancelDrag = () => finishCourtDrag(false);
    window.addEventListener("blur", cancelDrag);
    window.addEventListener("contextmenu", cancelDrag);
    return () => {
      window.removeEventListener("blur", cancelDrag);
      window.removeEventListener("contextmenu", cancelDrag);
    };
  }, [finishCourtDrag]);

  if (!list.length) return <div className={courtMode ? "minister-list minister-list-court" : "minister-list"}><div className="empty-note">{emptyNote}</div></div>;

  // 非朝班模式（全部tab）：普通网格
  if (!courtMode) {
    return (
      <div className="minister-list">
        {list.map((minister) => {
          const isCustom = minister.portrait_id?.startsWith("custom:");
          const dedicated = isCustom
            ? `/portraits/custom/${encodeURIComponent(minister.name)}?t=${cacheBust(minister.portrait_id!)}`
            : `/portraits/${portraitPrefix}${minister.id ?? minister.name}.png`;
          const poolFallback = !isCustom && minister.portrait_id ? `/portraits/${minister.portrait_id}.png` : undefined;
          const ousted = minister.status !== "active";
          const selectable = !selectionMode || (isSelectable ? isSelectable(minister) : true);
          const selectedForMeeting = selectionMode && selectedNames.includes(minister.name);
          return (
            <button key={minister.name}
              className={`minister-card ${selectedMinister === minister.name ? "selected" : ""} ${ousted ? "ousted" : ""} ${selectionMode ? "selecting" : ""} ${selectedForMeeting ? "meeting-selected" : ""} ${!selectable ? "meeting-disabled" : ""} ${draggableOrder ? "order-draggable" : ""}`}
              draggable={draggableOrder}
              onDragStart={(e) => {
                if (!draggableOrder) return;
                orderDragging.current = minister.name;
                didDrag.current = true;
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", minister.name);
              }}
              onDragOver={(e) => {
                if (!draggableOrder || !orderDragging.current || orderDragging.current === minister.name) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
              }}
              onDrop={(e) => {
                if (!draggableOrder) return;
                e.preventDefault();
                const fromName = orderDragging.current || e.dataTransfer.getData("text/plain");
                orderDragging.current = null;
                if (fromName && fromName !== minister.name) onReorder?.(fromName, minister.name);
              }}
              onDragEnd={() => {
                orderDragging.current = null;
                window.setTimeout(() => { didDrag.current = false; }, 0);
              }}
              onClick={() => {
                if (didDrag.current) return;
                if (selectionMode) {
                  if (selectable) onToggleSelect?.(minister);
                  return;
                }
                if (minister.archived) return;
                onOpenChat(minister);
              }}>
              <div className="minister-card-portrait-wrap">
                <MinisterPortrait primary={dedicated} fallback={poolFallback} name={minister.name} />
                {onUploadPortrait && <PortraitUploadButton ministerName={minister.name} onUpload={onUploadPortrait} />}
                {selectionMode && (
                  <span className={`minister-select-mark ${selectedForMeeting ? "checked" : ""}`}>
                    {selectedForMeeting ? <Check size={14} /> : null}
                  </span>
                )}
              </div>
              <div className="minister-card-info">
                <div className="minister-card-top">
                  <span className="minister-name">{minister.name}</span>
                  {ousted && <span className={`minister-status status-${minister.status}`}>{minister.status_label}</span>}
                  {minister.office && <span className="minister-office">{minister.office}</span>}
                </div>
                <span className="minister-bio">{minister.summary}</span>
              </div>
              {minister.favorite && <Star className="favorite-mark" size={13} />}
              {minister.archived && onRestoreMinister && (
                <span
                  className="minister-restore-action"
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRestoreMinister(minister);
                  }}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" && e.key !== " ") return;
                    e.preventDefault();
                    e.stopPropagation();
                    onRestoreMinister(minister);
                  }}
                >
                  <RotateCcw size={13} />
                  恢复
                </span>
              )}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="minister-list minister-list-court" ref={containerRef}>
      {list.map((minister) => {
        const isCustom = minister.portrait_id?.startsWith("custom:");
        const dedicated = isCustom
          ? `/portraits/custom/${encodeURIComponent(minister.name)}?t=${cacheBust(minister.portrait_id!)}`
          : `/portraits/${portraitPrefix}${minister.id ?? minister.name}.png`;
        const poolFallback = !isCustom && minister.portrait_id
          ? `/portraits/${minister.portrait_id}.png`
          : undefined;
        const ousted = minister.status !== "active";
        const selectable = !selectionMode || (isSelectable ? isSelectable(minister) : true);
        const selectedForMeeting = selectionMode && selectedNames.includes(minister.name);
        const pct = positions[minister.name];
        // 透视缩放：py=0最远最小，py=1最近最大
        const perspScale = pct ? 0.38 + 0.62 * pct.py : 1;
        // 卡片宽用 vh 单位（CSS），这里只控制 scale
        return (
          <button
            key={minister.name}
            className={`minister-card ${selectedMinister === minister.name ? "selected" : ""} ${ousted ? "ousted" : ""} ${selectionMode ? "selecting" : ""} ${selectedForMeeting ? "meeting-selected" : ""} ${!selectable ? "meeting-disabled" : ""}`}
            style={pct ? {
              position: "absolute",
              left: `${pct.px * 100}%`,
              top: `${pct.py * 100}%`,
              cursor: "grab",
              transform: `scale(${perspScale.toFixed(3)})`,
              transformOrigin: "bottom center",
              zIndex: Math.round(pct.py * 1000),
            } : { visibility: "hidden" }}
            onPointerDown={(e) => onCourtPointerDown(e, minister.name)}
            onPointerMove={onCourtPointerMove}
            onPointerUp={onCourtPointerEnd}
            onPointerCancel={onCourtPointerEnd}
            onLostPointerCapture={() => {
              if (dragging.current) finishCourtDrag(didDrag.current);
            }}
            onClick={(e) => {
              if (suppressNextClick.current || didDrag.current) {
                e.preventDefault();
                return;
              }
              if (selectionMode) {
                if (selectable) onToggleSelect?.(minister);
                return;
              }
              if (minister.archived) return;
              onOpenChat(minister);
            }}
          >
            <div className="minister-card-portrait-wrap">
              <MinisterPortrait primary={dedicated} fallback={poolFallback} name={minister.name} />
              {onUploadPortrait && (
                <PortraitUploadButton ministerName={minister.name} onUpload={onUploadPortrait} />
              )}
              {selectionMode && (
                <span className={`minister-select-mark ${selectedForMeeting ? "checked" : ""}`}>
                  {selectedForMeeting ? <Check size={14} /> : null}
                </span>
              )}
            </div>
            <div className="minister-card-info">
              <div className="minister-card-top">
                <span className="minister-name">{minister.name}</span>
                {ousted && <span className={`minister-status status-${minister.status}`}>{minister.status_label}</span>}
                {minister.office && <span className="minister-office">{minister.office}</span>}
              </div>
              <span className="minister-bio">{minister.summary}</span>
            </div>
            {minister.favorite && <Star className="favorite-mark" size={13} />}
            {minister.archived && onRestoreMinister && (
              <span
                className="minister-restore-action"
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  onRestoreMinister(minister);
                }}
                onKeyDown={(e) => {
                  if (e.key !== "Enter" && e.key !== " ") return;
                  e.preventDefault();
                  e.stopPropagation();
                  onRestoreMinister(minister);
                }}
              >
                <RotateCcw size={13} />
                恢复
              </span>
            )}
            {courtBubbles[minister.name] ? (
              <div className="court-speech-bubble" role="status">
                <b>{minister.name}</b>
                <span>{courtBubbles[minister.name]}</span>
              </div>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}


export function ArmyDrawer({
  armies,
  armsStock,
  troopRates,
  open,
  selectedArmyId,
  onSelectArmy,
  onClose,
}: {
  armies: Army[];
  armsStock?: ArmsStockItem[];
  troopRates?: Record<string, number>;
  open: boolean;
  selectedArmyId: string;
  onSelectArmy: (id: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = React.useState("");
  const mingArmies = armies.filter((a) => (a.owner_power || "ming") === "ming");
  const filtered = q ? mingArmies.filter((a) => a.name.includes(q) || a.station.includes(q) || a.commander.includes(q)) : mingArmies;
  const selected = mingArmies.find((a) => a.id === selectedArmyId) || null;
  const visibleStock = (armsStock || []).filter((w) => w.unlocked && w.qty > 0);
  const troopEntries = (army: Army) => Object.entries(army.troop_composition || {}).filter(([, amount]) => Number(amount) > 0);
  const troopCompositionText = (army: Army) => {
    const comp = army.troop_composition || {};
    const parts = Object.entries(comp).filter(([, amount]) => Number(amount) > 0);
    if (!parts.length) return army.troop_type || "—";
    return parts.map(([name, amount]) => `${name}${amount}`).join("、");
  };
  // 兵种单价来自后端 troop_rates（源自 troop_cost.json，单一来源；不再前端硬编码）。
  const troopRate = (name: string) => (troopRates && troopRates[name]) ?? 0.08;
  const troopMonthlyPay = (name: string, amount: number) => troopRate(name) * amount / 1000;
  const formatWan = (value: number) => {
    return value.toFixed(2);
  };
  const troopPayTotal = (army: Army) => {
    const entries = troopEntries(army);
    if (!entries.length) return 0;
    return entries.reduce((sum, [name, amount]) => sum + troopMonthlyPay(String(name), Number(amount)), 0);
  };
  // 某兵种持有的军械实物件数（军→兵种→装备：升级须有对应实物装备，按持械量定升级人数）。
  const troopArmsText = (army: Army, troopName: string) => {
    const held = (army.arms || []).filter((w) => w.troop_type === troopName && w.qty > 0);
    return held.length > 0 ? held.map((w) => `${w.name}×${w.qty}`).join("、") : "暂无";
  };
  const arrearsTone = (army: Army) => {
    const maint = army.maintenance_per_turn || 1;
    const months = army.arrears / maint;
    if (months >= 3) return "danger";
    if (months >= 1) return "warn";
    return "";
  };
  return (
    <RightDrawer open={open} onClose={onClose} title="军队" icon={<Swords size={17} />} extraClass="right-drawer-army">
      <div className="right-drawer-search">
        <input className="right-drawer-search-input" placeholder="搜索番号/驻地/统帅…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="arms-stock-tags" aria-label="兵部军备库存标签">
        {visibleStock.length ? visibleStock.map((w) => (
          <span key={w.id} className="arms-stock-tag" title={`${w.tier} · 库存 ${w.qty}`}>
            {w.name}<b>{w.qty}</b>
          </span>
        )) : (
          <span className="arms-stock-tag empty">军备总库空</span>
        )}
      </div>
      <div className="right-drawer-list">
        {filtered.map((army) => (
          <button
            key={army.id}
            className={`right-drawer-row${selectedArmyId === army.id ? " selected" : ""} ${arrearsTone(army)}`}
            onClick={() => onSelectArmy(army.id === selectedArmyId ? "" : army.id)}
          >
            <span className="right-drawer-row-name">{army.name}</span>
            <span className="right-drawer-row-meta">
              {army.manpower}兵 · {army.station}
            </span>
          </button>
        ))}
        {!filtered.length && <div className="empty-note">{q ? "无匹配结果。" : "暂无大明军队记录。"}</div>}
      </div>
      {selected && createPortal(
        <section className="army-detail-modal-layer" role="dialog" aria-modal="true" aria-label={`${selected.name}军队详情`}>
          <div className="army-detail-modal-scrim" onClick={() => onSelectArmy("")} />
          <div className="army-detail-modal">
            <header className="army-detail-modal-header">
              <div>
                <h2>{selected.name}</h2>
                <span>{selected.station} · {selected.theater}</span>
              </div>
              <button className="region-modal-close" onClick={() => onSelectArmy("")} aria-label="关闭详情"><X size={18} /></button>
            </header>
            <div className="army-detail-modal-body">
              <table className="intel-table army-detail-table">
                <tbody>
                  <tr><th>统帅</th><td>{selected.commander || "—"}</td><th>主管</th><td>{selected.controller || "—"}</td></tr>
                  <tr><th>兵种</th><td colSpan={3}>{selected.troop_type}</td></tr>
                  <tr><th>编制</th><td colSpan={3}>{troopCompositionText(selected)}</td></tr>
                  <tr><th>兵力</th><td>{selected.manpower}</td><th>月饷</th><td>{selected.maintenance_per_turn}万两（分项{formatWan(troopPayTotal(selected))}）</td></tr>
                  <tr><th>补给</th><td>{selected.supply}</td><th>士气</th><td>{selected.morale}</td></tr>
                  <tr><th>操练</th><td>{selected.training}</td><th>机动</th><td>{selected.mobility}</td></tr>
                  <tr><th>忠诚</th><td colSpan={3}>{selected.loyalty}</td></tr>
                  <tr><th>欠饷</th><td colSpan={3}>{selected.arrears > 0 ? `${selected.arrears}万两（≈${(selected.arrears / (selected.maintenance_per_turn || 1)).toFixed(1)}月）` : "无欠饷"}</td></tr>
                  <tr><th>状态</th><td colSpan={3}>{selected.status}</td></tr>
                </tbody>
              </table>
              <table className="intel-table army-troop-table">
                <thead>
                  <tr><th>兵种</th><th>人数</th><th>单价</th><th>月饷</th><th>装备</th></tr>
                </thead>
                <tbody>
                  {(troopEntries(selected).length ? troopEntries(selected) : [[selected.troop_type || "未分兵种", selected.manpower]]).map(([name, amount]) => {
                    const troopName = String(name);
                    const rate = troopRate(troopName);
                    const monthlyPay = troopMonthlyPay(troopName, Number(amount));
                    return (
                      <tr key={troopName}>
                        <td>{name}</td>
                        <td>{Number(amount)}</td>
                        <td>{rate.toFixed(2)}万/千人</td>
                        <td>{formatWan(monthlyPay)}万两</td>
                        <td>{troopArmsText(selected, troopName)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>,
        document.body
      )}
    </RightDrawer>
  );
}

export function RegionDrawer({
  regions,
  open,
  selectedRegionId,
  onSelectRegion,
  onClose,
}: {
  regions: Region[];
  open: boolean;
  selectedRegionId: string;
  onSelectRegion: (id: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = React.useState("");
  const mingRegions = regions.filter((r) => (r.controlled_by || "ming") === "ming");
  const filtered = q ? mingRegions.filter((r) => r.name.includes(q)) : mingRegions;
  const regionTone = (r: Region) => {
    if (r.unrest >= 70) return "danger";
    if (r.unrest >= 45) return "warn";
    return "";
  };
  return (
    <RightDrawer open={open} onClose={onClose} title="省份" icon={<MapPinned size={17} />} extraClass="right-drawer-region">
      <div className="right-drawer-search">
        <input className="right-drawer-search-input" placeholder="搜索省份名…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="right-drawer-list">
        {filtered.map((r) => (
          <button
            key={r.id}
            className={`right-drawer-row${selectedRegionId === r.id ? " selected" : ""} ${regionTone(r)}`}
            onClick={() => onSelectRegion(r.id === selectedRegionId ? "" : r.id)}
          >
            <span className="right-drawer-row-name">{r.name}</span>
            <span className="right-drawer-row-meta">
              动乱{r.unrest} · 实收{regionMonthlyTax(r)}万
            </span>
          </button>
        ))}
        {!filtered.length && <div className="empty-note">{q ? "无匹配结果。" : "暂无大明省份记录。"}</div>}
      </div>
    </RightDrawer>
  );
}

export function RegionDetailModal({
  region,
  onClose,
}: {
  region: Region;
  onClose: () => void;
}) {
  const fiscalValue = (r: Region, key: string) => Number(r.fiscal?.[key] ?? 0);
  const taxPart = (r: Region, key: string) => Number(r.tax_breakdown?.[key] ?? 0);
  return (
    <div className="region-modal-layer" role="dialog" aria-modal="true" aria-label={region.name}>
      <div className="region-modal-scrim" onClick={onClose} />
      <div className="region-modal">
        <div className="region-modal-header">
          <div>
            <h2>{region.name}</h2>
            <span>{region.kind} · {region.controlled_by || "ming"}</span>
          </div>
          <button className="region-modal-close" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="region-modal-body">
          <table className="intel-table">
            <tbody>
            <tr><th>编号</th><td>{region.id}</td><th>类型</th><td>{region.kind}</td></tr>
            <tr><th>归属</th><td>{region.controlled_by || "ming"}</td><th>人口</th><td>{region.population}万</td></tr>
            <tr><th>民心</th><td>{region.public_support}</td><th>动乱</th><td>{region.unrest}</td></tr>
            <tr><th>粮食年产</th><td>{fiscalValue(region, "grain_output")}万石</td><th>可调余粮</th><td>{fiscalValue(region, "grain_stock")}万石</td></tr>
            <tr><th>边防压力</th><td colSpan={3}>{region.military_pressure}</td></tr>
            <tr><th className="intel-section-th" colSpan={4}>在册田亩 {region.registered_land}万亩 · 黄册登记田（官民田＋藩王庄田＋皇庄），仅官民田纳国库田赋</th></tr>
            <tr><th>├ 官民田<span className="intel-th-note">（→国库田赋）</span></th><td>{fiscalValue(region, "guan_min_tian")}万亩</td><th>├ 藩王庄田<span className="intel-th-note">（免税）</span></th><td>{fiscalValue(region, "wang_tian")}万亩</td></tr>
            <tr><th>└ 皇庄<span className="intel-th-note">（→内库地租）</span></th><td>{fiscalValue(region, "huang_tian")}万亩</td><th>隐田<span className="intel-th-note">（缙绅诡寄＋藩王侵占，册外逃赋）</span></th><td>{region.hidden_land}万亩</td></tr>
            <tr><th>士绅阻力</th><td>{region.gentry_resistance}</td><th>腐败度</th><td>{fiscalValue(region, "corruption")}</td></tr>
            <tr><th className="intel-section-th" colSpan={4}>税收 · 田赋亩率 {fiscalValue(region, "tian_fu_li") || 250}毫/亩·年（{((fiscalValue(region, "tian_fu_li") || 250) / 10000).toFixed(3)}两）· 实收效率 {Math.round((region.tax_efficiency ?? 0) * 100)}%</th></tr>
            <tr><th>田赋账面</th><td>{region.tax_per_turn}万/月</td><th>四税实收</th><td>{regionMonthlyTax(region)}万/月</td></tr>
            <tr><th>田赋实收</th><td>{taxPart(region, "田赋")}万</td><th>辽饷实收</th><td>{taxPart(region, "辽饷")}万</td></tr>
            <tr><th>盐税实收</th><td>{taxPart(region, "盐税")}万</td><th>商税实收</th><td>{taxPart(region, "商税")}万</td></tr>
            <tr><th>辽饷基数</th><td>{fiscalValue(region, "liao_xiang")}万/月</td><th>盐税基数</th><td>{fiscalValue(region, "salt_tax")}万/月</td></tr>
            <tr><th>商税基数</th><td>{fiscalValue(region, "commerce_tax")}万/月</td><th>皇庄地租<span className="intel-th-note">（内库）</span></th><td>{taxPart(region, "皇庄")}万</td></tr>
            <tr><th>天灾</th><td colSpan={3}>{region.natural_disaster}</td></tr>
            <tr><th>人祸</th><td colSpan={3}>{region.human_disaster}</td></tr>
            <tr><th>状况</th><td colSpan={3}>{region.status}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function BuildingDrawer({
  regions,
  mapNodes,
  technologies,
  open,
  onClose,
}: {
  regions: Region[];
  mapNodes: MapNode[];
  technologies: Technology[];
  open: boolean;
  onClose: () => void;
}) {
  const [tab, setTab] = React.useState<"建筑" | "科技">("建筑");
  const allBuildings: (Building & { regionName: string })[] = [];
  for (const node of mapNodes) {
    if (!node.buildings) continue;
    const regionName = node.region?.name || node.label || node.id;
    for (const b of node.buildings) {
      allBuildings.push({ ...b, regionName });
    }
  }
  const [filterRegion, setFilterRegion] = React.useState("");
  const [q, setQ] = React.useState("");
  const regionNames = Array.from(new Set(allBuildings.map((b) => b.regionName)));
  const filtered = allBuildings
    .filter((b) => !filterRegion || b.regionName === filterRegion)
    .filter((b) => !q || b.name.includes(q) || b.category.includes(q));
  const techFiltered = (technologies || []).filter((t) => !q || t.name.includes(q) || t.category.includes(q));
  return (
    <RightDrawer open={open} onClose={onClose} title="工部" icon={<Landmark size={17} />} extraClass="right-drawer-building">
      <div className="segmented right-drawer-segmented">
        {(["建筑", "科技"] as const).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      <div className="right-drawer-search">
        <input
          className="right-drawer-search-input"
          placeholder={tab === "建筑" ? "搜索建筑名/类别…" : "搜索科技名/类别…"}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      {tab === "建筑" ? (
        <>
          <div className="right-drawer-filter">
            <select
              value={filterRegion}
              onChange={(e) => setFilterRegion(e.target.value)}
              className="right-drawer-select"
            >
              <option value="">全部省份</option>
              {regionNames.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="right-drawer-list">
            {filtered.map((b) => (
              <div key={b.id} className="right-drawer-row right-drawer-row-building">
                <span className="right-drawer-row-name">{b.name}</span>
                <span className="right-drawer-row-meta">{b.regionName} · {b.category} Lv{b.level}</span>
                <span className="right-drawer-row-sub">
                  完好{b.condition} · 维护{b.maintenance}万/月
                  {b.output_metric ? ` · ${b.output_metric}+${b.output_amount}` : ""}
                </span>
              </div>
            ))}
            {!filtered.length && <div className="empty-note">{q || filterRegion ? "无匹配结果。" : "暂无建筑记录。"}</div>}
          </div>
        </>
      ) : (
        <div className="right-drawer-list">
          {techFiltered.map((t) => (
            <div key={t.id} className="right-drawer-row right-drawer-row-building">
              <span className="right-drawer-row-name">{t.name}</span>
              <span className="right-drawer-row-meta">{t.category}</span>
              {(t.effect_summary || t.status) && (
                <span className="right-drawer-row-sub">{t.effect_summary || t.status}</span>
              )}
            </div>
          ))}
          {!techFiltered.length && <div className="empty-note">{q ? "无匹配结果。" : "暂无已解锁科技。"}</div>}
        </div>
      )}
    </RightDrawer>
  );
}

export function EconomyDrawer({
  state,
  open,
  onClose,
}: {
  state: GameState;
  open: boolean;
  onClose: () => void;
}) {
  const [tab, setTab] = React.useState<"国库" | "内库">("国库");
  const [q, setQ] = React.useState("");
  const budget = state.budget[tab];
  const modifierPct = budget.modifier_pct || 0;
  const hasModifier = modifierPct !== 0 && budget.base_net !== undefined;
  const budgetFormula = (item: { base?: number; rate?: number; amount: number; note?: string; formula?: string; formula_kind?: string }) =>
    item.formula ? `${item.formula_kind === "per_basis" ? "税基" : "基准"} ${item.formula} = ${formatMoney(item.amount)}` : (item.note || "");
  const matchItem = (name: string, extra = "") => !q || `${name} ${extra}`.includes(q);
  return (
    <RightDrawer open={open} onClose={onClose} title="经济" icon={<ScrollText size={17} />} extraClass="right-drawer-economy">
      <div className="segmented right-drawer-segmented">
        {(["国库", "内库"] as const).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      <div className="right-drawer-search">
        <input className="right-drawer-search-input" placeholder="搜索收支项…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="right-drawer-economy-summary">
        <span>余额 <b>{formatMoney(budget.balance)}</b></span>
        <span className={budget.net >= 0 ? "income" : "expense"}>
          月净 <b>{formatSignedMoney(budget.net)}</b>
        </span>
        {hasModifier && (
          <span className="budget-base-note">
            基准 {formatSignedMoney(budget.base_net || 0)} / 修正 {modifierPct > 0 ? "+" : ""}{modifierPct}%
          </span>
        )}
      </div>
      <div className="right-drawer-list">
        <div className="right-drawer-section-title">固定收入</div>
        {budget.income.filter((item) => matchItem(item.name, `${item.note || ""} ${item.base_key || ""} ${item.rate_key || ""}`)).map((item) => (
          <div key={`in-${item.name}`} className="right-drawer-budget-row">
            <span>
              <b>{item.name}</b>
              {item.formula && <small>{budgetFormula(item)}</small>}
            </span>
            <b className="income">+{formatMoney(item.amount)}</b>
          </div>
        ))}
        <div className="right-drawer-section-title">固定支出</div>
        {budget.expense.filter((item) => matchItem(item.name, `${item.note || ""} ${item.base_key || ""} ${item.rate_key || ""}`)).map((item) => (
          <div key={`ex-${item.name}`} className="right-drawer-budget-row">
            <span>
              <b>{item.name}</b>
              {item.formula && <small>{budgetFormula(item)}</small>}
            </span>
            <b className="expense">-{formatMoney(item.amount)}</b>
          </div>
        ))}
        {budget.movements.filter((m) => matchItem(m.category || m.reason)).length > 0 && (
          <>
            <div className="right-drawer-section-title">本月一次性入账</div>
            {budget.movements.filter((m) => matchItem(m.category || m.reason)).map((m, i) => (
              <div key={`mv-${i}`} className="right-drawer-budget-row">
                <span>{m.category || m.reason}</span>
                <b className={m.delta >= 0 ? "income" : "expense"}>{formatSignedMoney(m.delta)}</b>
              </div>
            ))}
          </>
        )}
      </div>
    </RightDrawer>
  );
}

export function AppointmentDrawer({
  ministers,
  departments = [],
  open,
  onOpenChat,
  onClose,
}: {
  ministers: Minister[];
  departments?: Department[];
  open: boolean;
  onOpenChat: (minister: Minister) => void;
  onClose: () => void;
}) {
  const [q, setQ] = React.useState("");
  const [detailMinister, setDetailMinister] = React.useState<Minister | null>(null);
  const BASE_OFFICES = ["内阁", "吏部", "户部", "礼部", "兵部", "刑部", "工部"];
  const departmentNames = new Set(departments.map((d) => (d.name || "").trim()).filter(Boolean));
  // 新设衙门（军机处/情报司等）以 DB 部门表为准；兼容旧存档里只有在职大臣 office_type 的动态部门。
  const extraOffices = [...new Set(
    [
      ...departments.map((d) => (d.name || "").trim()),
      ...ministers
        .filter((m) => (m.power_id || "ming") === "ming" && m.status === "active")
        .map((m) => (m.office_type || "").trim()),
    ].filter((t) => t && t !== "后宫" && !BASE_OFFICES.includes(t))
  )];
  const offices = [...BASE_OFFICES, ...extraOffices];
  const byOffice = new Map<string, Minister[]>();
  for (const office of offices) byOffice.set(office, []);
  byOffice.set("其他", []);
  for (const m of ministers) {
    if ((m.power_id || "ming") !== "ming") continue;
    if (m.status !== "active") continue;
    if (q && !m.name.includes(q) && !(m.office || "").includes(q) && !(m.office_type || "").includes(q)) continue;
    // 先精确匹配 office_type（新设衙门名完整），再回退包含匹配（基础六部容旧标签变体）
    const exact = offices.find((o) => (m.office_type || "").trim() === o);
    const matched = exact || BASE_OFFICES.find((o) => (m.office_type || "").includes(o));
    const key = matched || "其他";
    byOffice.get(key)!.push(m);
  }
  return (
    <RightDrawer open={open} onClose={onClose} title="官员任免" icon={<Star size={17} />} extraClass="right-drawer-appointment">
      <div className="right-drawer-search">
        <input className="right-drawer-search-input" placeholder="搜索姓名/职位…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="right-drawer-list">
        {[...offices, "其他"].map((office) => {
          const group = byOffice.get(office) || [];
          if (!group.length && (office === "其他" || !departmentNames.has(office))) return null;
          return (
            <div key={office}>
              <div className="right-drawer-section-title">{office}</div>
              {group.length ? group.map((m) => (
                <button
                  key={m.name}
                  className="right-drawer-row right-drawer-row-minister"
                  onClick={() => onOpenChat(m)}
                >
                  <span className="right-drawer-row-action">
                    <button
                      type="button"
                      className="minister-detail-open"
                      aria-label={`查看${m.name}详情`}
                      title="查看详情"
                      onClick={(event) => {
                        event.stopPropagation();
                        setDetailMinister(m);
                      }}
                    >
                      <Info size={14} />
                    </button>
                  </span>
                  <div className="right-drawer-minister-row">
                    <span className="right-drawer-row-name">{m.name}</span>
                    <span className="right-drawer-minister-office">{m.office || m.office_type}</span>
                  </div>
                </button>
              )) : <div className="empty-note">暂无在职官员。</div>}
            </div>
          );
        })}
        {[...offices, "其他"].every((o) => !(byOffice.get(o) || []).length) && (
          <div className="empty-note">{q ? "无匹配结果。" : "暂无在职官员。"}</div>
        )}
      </div>
      {detailMinister ? <MinisterDetailDialog minister={detailMinister} onClose={() => setDetailMinister(null)} /> : null}
    </RightDrawer>
  );
}

export function MinisterDetailDialog({
  minister,
  onClose,
}: {
  minister: Minister;
  onClose: () => void;
}) {
  const lifeText = minister.birth_year
    ? `${minister.birth_year}年生${minister.historical_death_year ? ` · ${minister.historical_death_year}年${minister.historical_death_month ? `${minister.historical_death_month}月` : ""}卒` : ""}`
    : (minister.historical_death_year ? `${minister.historical_death_year}年${minister.historical_death_month ? `${minister.historical_death_month}月` : ""}卒` : "未载");
  const debutText = minister.debut_year
    ? `${minister.debut_year}年${minister.debut_month ? `${minister.debut_month}月` : ""}`
    : "开局在场或未指定";
  const isCustom = minister.portrait_id?.startsWith("custom:");
  const portraitPrimary = isCustom
    ? `/portraits/custom/${encodeURIComponent(minister.name)}?t=${cacheBust(minister.portrait_id!)}`
    : `/portraits/minister_${minister.id ?? minister.name}.png`;
  const portraitFallback = !isCustom && minister.portrait_id ? `/portraits/${minister.portrait_id}.png` : undefined;
  const formatSkill = (skill: Minister["skills"][number]) => {
    const label = skill.name || (skill.kind === "tool" ? "可用工具" : "可用能力");
    const descriptionText = skill.description ? `：${skill.description}` : "";
    return `${label}${descriptionText}`;
  };
  const formatFieldValue = (key: string, value: unknown): string => {
    if (key === "skills" && Array.isArray(value)) {
      return value.length ? value.map((item) => formatSkill(item as Minister["skills"][number])).join("\n") : "无";
    }
    if (Array.isArray(value)) {
      return value.map((item) => {
        if (item && typeof item === "object") return JSON.stringify(item);
        return String(item);
      }).join("\n");
    }
    if (value && typeof value === "object") return JSON.stringify(value);
    return String(value);
  };
  const skillText = minister.skills?.length
    ? minister.skills.filter((skill) => skill.kind === "agno_skill").map(formatSkill).join("\n") || "无"
    : "无";
  const toolText = minister.skills?.length
    ? minister.skills.filter((skill) => skill.kind === "tool").map(formatSkill).join("\n") || "无"
    : "无";
  const showDebugFields = new URLSearchParams(window.location.search).get("debug") === "1";
  const allFields = showDebugFields
    ? Object.entries(minister)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => [key, formatFieldValue(key, value)])
    : [];
  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;
  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  const dialog = (
    <div className="minister-detail-layer" role="dialog" aria-modal="true" aria-label={`人物详情：${minister.name}`}>
      <div className="minister-detail-scrim" onClick={onClose} />
      <section className="minister-detail-dialog" onClick={(event) => event.stopPropagation()}>
        <header className="minister-detail-header">
          <div>
            <span className={`minister-status status-${minister.status}`}>{minister.status_label || minister.status}</span>
            <h2>{minister.name}</h2>
            <p>{minister.summary}</p>
          </div>
          <button className="icon-button" aria-label="关闭人物详情" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <div className="minister-detail-body">
          <div className="minister-detail-layout">
            <div className="minister-detail-portrait">
              <MinisterPortrait primary={portraitPrimary} fallback={portraitFallback} name={minister.name} />
            </div>
            <table className="intel-table minister-detail-table">
              <tbody>
                <tr><th>姓名</th><td>{minister.name}</td><th>官职</th><td>{minister.office || "无"}</td></tr>
                <tr><th>官署</th><td>{minister.office_type || "未载"}</td><th>派系</th><td>{minister.faction || "未载"}</td></tr>
                <tr><th>行事</th><td>{minister.style || "未载"}</td><th>势力</th><td>{minister.power_id || "ming"}</td></tr>
                <tr><th>状态</th><td>{minister.status_label || minister.status || "未载"}</td><th>原因</th><td>{minister.status_reason || "无"}</td></tr>
                <tr><th>所在</th><td>{minister.location || "未载"}</td><th>头像</th><td>{minister.portrait_id || "默认"}</td></tr>
                <tr><th>生卒</th><td>{lifeText}</td><th>登场</th><td>{debutText}</td></tr>
                <tr><th>忠诚</th><td>{minister.loyalty ?? "未载"}</td><th>才干</th><td>{minister.ability ?? "未载"}</td></tr>
                <tr><th>操守</th><td>{minister.integrity ?? "未载"}</td><th>胆略</th><td>{minister.courage ?? "未载"}</td></tr>
                <tr><th>外交</th><td>{minister.diplomacy ?? "未载"}</td><th>军事</th><td>{minister.martial ?? "未载"}</td></tr>
                <tr><th>管理</th><td>{minister.stewardship ?? "未载"}</td><th>谋略</th><td>{minister.intrigue ?? "未载"}</td></tr>
                <tr><th>学识</th><td>{minister.learning ?? "未载"}</td><th></th><td></td></tr>
                <tr><th className="intel-section-th" colSpan={4}>人物简介</th></tr>
                <tr><td colSpan={4}>{minister.description || minister.summary || "未载。"}</td></tr>
                <tr><th>别名</th><td colSpan={3}>{minister.aliases?.length ? minister.aliases.join("、") : "无"}</td></tr>
                <tr><th>个人技艺</th><td colSpan={3}>{minister.personal_skills?.length ? minister.personal_skills.join("、") : "无"}</td></tr>
                <tr><th className="intel-section-th" colSpan={4}>可用能力</th></tr>
                <tr><td colSpan={4}><pre className="minister-detail-pre">{skillText}</pre></td></tr>
                <tr><th className="intel-section-th" colSpan={4}>可用工具</th></tr>
                <tr><td colSpan={4}><pre className="minister-detail-pre">{toolText}</pre></td></tr>
              </tbody>
            </table>
          </div>
          {showDebugFields ? (
            <details className="minister-detail-raw">
              <summary>全部字段</summary>
              <table className="intel-table minister-detail-table">
                <tbody>
                {allFields.map(([key, value]) => (
                  <tr key={key}>
                    <th>{key}</th>
                    <td colSpan={3}>{value}</td>
                  </tr>
                ))}
                </tbody>
              </table>
            </details>
          ) : null}
        </div>
      </section>
    </div>
  );
  return createPortal(dialog, document.body);
}

export function CourtDrawer({
  state: _state,
  ministers,
  ministerGroup,
  selectedMinister,
  open,
  onGroupChange,
  onClose,
  onOpenChat,
  onRestoreMinister,
  onUploadPortrait,
  courtChatHistory,
  courtChatInput,
  courtChatBusy,
  courtChatError,
  courtChatBubbles,
  courtChatPanelOpen,
  courtChatLiveMessages,
  courtChatDecision,
  courtChatSelectedMinisters,
  courtChatStreamSpeed,
  onCourtChatSelectedMinistersChange,
  onCourtChatInputChange,
  onCourtChatStreamSpeedChange,
  onSendCourtChat,
  onStopCourtChat,
  onSummarizeCourtChat,
  onRefreshCourtChat,
  onCloseCourtChatPanel,
  onChooseCourtChatDecision,
}: {
  state: GameState;
  ministers: Minister[];
  ministerGroup: string;
  selectedMinister: string;
  open: boolean;
  onGroupChange: (group: string) => void;
  onClose: () => void;
  onOpenChat: (minister: Minister) => void;
  onRestoreMinister?: (minister: Minister) => void;
  onUploadPortrait: (ministerName: string, file: File) => Promise<void>;
  courtChatHistory: CourtChatMessage[];
  courtChatInput: string;
  courtChatBusy: boolean;
  courtChatError: string;
  courtChatBubbles: Record<string, string>;
  courtChatPanelOpen: boolean;
  courtChatLiveMessages: CourtChatMessage[];
  courtChatDecision: CourtChatMessage | null;
  courtChatSelectedMinisters: string[];
  courtChatStreamSpeed: number;
  onCourtChatSelectedMinistersChange: React.Dispatch<React.SetStateAction<string[]>>;
  onCourtChatInputChange: (value: string) => void;
  onCourtChatStreamSpeedChange: (value: number) => void;
  onSendCourtChat: (ministers: Minister[], overrideMessage?: string) => void;
  onStopCourtChat: () => void;
  onSummarizeCourtChat: (ministers: Minister[]) => void;
  onRefreshCourtChat: () => void;
  onCloseCourtChatPanel: () => void;
  onChooseCourtChatDecision: (option: string) => void;
}) {
  const [q, setQ] = React.useState("");
  const [showHistory, setShowHistory] = React.useState(false);
  const [courtChatStep, setCourtChatStep] = React.useState<"closed" | "composing">("closed");
  const [meetingSelectionMode, setMeetingSelectionMode] = React.useState(false);
  const [meetingSelectedNames, setMeetingSelectedNames] = React.useState<string[]>([]);
  const [activeMinisterOrder, setActiveMinisterOrder] = React.useState<string[]>(() => {
    try {
      const raw = localStorage.getItem("ming-active-minister-order");
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter((name) => typeof name === "string") : [];
    } catch {
      return [];
    }
  });
  const courtChatPanelBodyRef = React.useRef<HTMLDivElement | null>(null);
  const cleanCourtChatText = (value: string) => value.replace(/\s*<<<臣:([^>\n]+)>>+\s*/g, "\n$1：").trim();
  const orderIndex = new Map(activeMinisterOrder.map((name, index) => [name, index]));
  const orderedMinisters = ministerGroup === "在职"
    ? [...ministers].sort((a, b) => {
      const ai = orderIndex.has(a.name) ? orderIndex.get(a.name)! : Number.MAX_SAFE_INTEGER;
      const bi = orderIndex.has(b.name) ? orderIndex.get(b.name)! : Number.MAX_SAFE_INTEGER;
      if (ai !== bi) return ai - bi;
      return ministers.indexOf(a) - ministers.indexOf(b);
    })
    : ministers;
  const filtered = q ? orderedMinisters.filter((m) => m.name.includes(q) || (m.office || "").includes(q)) : orderedMinisters;
  const activeFiltered = filtered.filter(canAttendCourtChat);
  const activeAll = ministers.filter(canAttendCourtChat);
  const activeAllNames = activeAll.map((m) => m.name);
  const activeNames = activeFiltered.map((m) => m.name);
  const rosterModes = ministerGroup === "内阁+六部" || ministerGroup === "收藏";
  const activeMeetingSelection = ministerGroup === "在职" && meetingSelectionMode;
  const selectedNames = courtChatSelectedMinisters.filter((name) => (
    activeMeetingSelection ? activeAllNames.includes(name) : activeNames.includes(name)
  ));
  const courtChatAvailable = rosterModes || activeMeetingSelection;
  const canChat = open && courtChatAvailable && selectedNames.length > 0;
  const courtChatRoster = activeMeetingSelection ? activeAll : activeFiltered;
  const activeIssues = _state.issues.filter((i) => i.kind === "situation" || i.kind === "initiative");
  const setMeetingSelection = (names: string[]) => {
    const next = names.filter((name, index) => activeAllNames.includes(name) && names.indexOf(name) === index);
    setMeetingSelectedNames(next);
    onCourtChatSelectedMinistersChange(next);
  };
  const toggleMeetingMinister = (minister: Minister) => {
    if (!canAttendCourtChat(minister)) return;
    setMeetingSelection(
      meetingSelectedNames.includes(minister.name)
        ? meetingSelectedNames.filter((name) => name !== minister.name)
        : [...meetingSelectedNames, minister.name],
    );
  };
  const startMeetingSelection = () => {
    setMeetingSelection(meetingSelectedNames);
    setMeetingSelectionMode(true);
    setCourtChatStep("composing");
  };
  const reorderActiveMinister = (fromName: string, toName: string) => {
    const visibleNames = filtered.map((m) => m.name);
    if (!visibleNames.includes(fromName) || !visibleNames.includes(toName)) return;
    const knownNames = ministers.map((m) => m.name);
    const current = [
      ...activeMinisterOrder.filter((name) => knownNames.includes(name)),
      ...knownNames.filter((name) => !activeMinisterOrder.includes(name)),
    ];
    const fromIndex = current.indexOf(fromName);
    const toIndex = current.indexOf(toName);
    if (fromIndex < 0 || toIndex < 0) return;
    const next = [...current];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    setActiveMinisterOrder(next);
    localStorage.setItem("ming-active-minister-order", JSON.stringify(next));
  };
  const pickCourtChatTopic = (issue: Issue) => {
    const opener = `众卿，关于「${issue.title}」一事，${issue.stage_text}。诸卿有何对策？`;
    onCourtChatInputChange(opener);
    onSendCourtChat(courtChatRoster, opener);
  };
  React.useEffect(() => {
    if (!open) return;
    onRefreshCourtChat();
  }, [open, onRefreshCourtChat]);
  React.useEffect(() => {
    const el = courtChatPanelBodyRef.current;
    if (!el || !courtChatPanelOpen) return;
    el.scrollTop = el.scrollHeight;
  }, [courtChatPanelOpen, courtChatLiveMessages]);
  React.useEffect(() => {
    if (!courtChatAvailable || !activeFiltered.length) {
      setCourtChatStep("closed");
      return;
    }
    if (rosterModes) {
      onCourtChatSelectedMinistersChange(activeNames);
    } else {
      const next = meetingSelectedNames.filter((name) => activeAllNames.includes(name));
      setMeetingSelectedNames(next);
      onCourtChatSelectedMinistersChange(next);
    }
    setCourtChatStep("composing");
  }, [courtChatAvailable, rosterModes, ministerGroup, open, activeNames.join("|"), activeAllNames.join("|"), meetingSelectedNames.join("|"), onCourtChatSelectedMinistersChange]);
  React.useEffect(() => {
    if (ministerGroup !== "在职") {
      setMeetingSelectionMode(false);
    }
  }, [ministerGroup]);
  return (
    <>
      {open && <button className="drawer-scrim" aria-label="收起" onClick={onClose} />}
      <aside className={`court-drawer ${open ? "open" : ""}`}>
        <div className="drawer-brand">
          <div className="panel-title">
            <Landmark size={17} />
            <span>朝堂</span>
          </div>
          <button className="icon-button" aria-label="收起" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="segmented">
          {["内阁+六部", "收藏", "在职", "全部", "已归档"].map((group) => (
            <button
              className={ministerGroup === group ? "active" : ""}
              key={group}
              onClick={() => onGroupChange(group)}
            >
              {group}
            </button>
          ))}
        </div>
        <div className="right-drawer-search court-search">
          <input className="right-drawer-search-input" placeholder="搜索姓名/职位…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {ministerGroup === "在职" ? (
          <div className="court-meeting-toolbar">
            <button
              type="button"
              className={`court-meeting-start ${meetingSelectionMode ? "active" : ""}`}
              disabled={!activeFiltered.length}
              onClick={() => {
                if (meetingSelectionMode) {
                  setMeetingSelectionMode(false);
                  setCourtChatStep("closed");
                  return;
                }
                startMeetingSelection();
              }}
            >
              <MessageSquareText size={15} />
              <span>{meetingSelectionMode ? "退出御前会议" : "御前会议"}</span>
            </button>
            {meetingSelectionMode ? (
              <>
                <span className="court-meeting-count">已选 {selectedNames.length} / {activeFiltered.length}</span>
                <button type="button" className="court-meeting-link" onClick={() => setMeetingSelection(activeAllNames)}>全选</button>
                <button type="button" className="court-meeting-link" onClick={() => setMeetingSelection([])}>清空</button>
              </>
            ) : (
              <span className="court-meeting-count">多选在职大臣入会</span>
            )}
          </div>
        ) : null}
        <MinisterCardList
          list={filtered}
          portraitPrefix="minister_"
          selectedMinister={selectedMinister}
          emptyNote={q ? "无匹配大臣。" : "此栏暂无可召见大臣。"}
          onOpenChat={onOpenChat}
          onRestoreMinister={onRestoreMinister}
          courtMode={ministerGroup === "内阁+六部" || ministerGroup === "收藏"}
          onUploadPortrait={onUploadPortrait}
          courtBubbles={courtChatPanelOpen ? {} : courtChatBubbles}
          selectionMode={activeMeetingSelection}
          selectedNames={meetingSelectionMode ? meetingSelectedNames : courtChatSelectedMinisters}
          onToggleSelect={toggleMeetingMinister}
          isSelectable={canAttendCourtChat}
          draggableOrder={ministerGroup === "在职"}
          onReorder={reorderActiveMinister}
        />
        {courtChatPanelOpen ? (
          <>
            <div className="court-chat-panel-scrim" aria-hidden="true" />
            <section className="court-chat-panel" role="dialog" aria-modal="false" aria-label="朝会群臣奏对">
              <header className="court-chat-panel-head">
                <div>
                  <b>朝会群臣</b>
                  <span>{courtChatBusy ? "群臣奏对中，陛下可随时发话" : "御前会议"}</span>
                </div>
                <button className="icon-button" onClick={onCloseCourtChatPanel} aria-label="关闭朝会奏对"><X size={15} /></button>
              </header>
              <div className="court-chat-panel-body" ref={courtChatPanelBodyRef}>
                {courtChatLiveMessages.map((m, i) => (
                  <article key={`${m.speaker}-${i}-${m.content}`} className={`court-chat-panel-line ${m.role}`}>
                    <CourtChatAvatar message={m} />
                    <div className="court-chat-message-stack">
                      <div className="court-chat-panel-speaker">
                        {m.role === "emperor" ? "朕" : m.role === "conclusion" ? "朝议结论" : m.speaker}
                      </div>
                      <div className="court-chat-panel-bubble">
                        <p>{m.displayContent ?? m.content}</p>
                      </div>
                    </div>
                  </article>
                ))}
                {courtChatBusy ? <div className="court-chat-panel-thinking">殿上诸臣正相继出班...</div> : null}
                {!courtChatBusy && courtChatDecision?.options?.length ? (
                  <div className="court-chat-decision">
                    <div className="court-chat-decision-head">
                      <b>请陛下裁断</b>
                      <span>选择一案转入诏书草案</span>
                    </div>
                    <div className="court-chat-decision-options">
                      {courtChatDecision.options.map((option, index) => (
                        <button key={`${index}-${option}`} type="button" onClick={() => onChooseCourtChatDecision(option)}>
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
              <footer className="court-chat-panel-composer">
                <div className="court-chat-speed-control" title="调整朝会流式输出速度">
                  <span>奏对速度</span>
                  <input
                    type="range"
                    min={1}
                    max={5}
                    step={1}
                    value={courtChatStreamSpeed}
                    onChange={(e) => onCourtChatStreamSpeedChange(Number(e.target.value))}
                    aria-label="朝会流式输出速度"
                  />
                  <b>{courtChatStreamSpeed}</b>
                </div>
                <button className="court-chat-history-btn" onClick={() => setShowHistory((v) => !v)} title="查看本月朝会聊天历史">
                  <MessageSquareText size={16} />
                  <span>{courtChatHistory.length}</span>
                </button>
                <textarea
                  className="court-chat-input"
                  value={courtChatInput}
                  placeholder={courtChatBusy ? "朕要插一句..." : "垂询群臣..."}
                  rows={1}
                  onChange={(e) => onCourtChatInputChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      onSendCourtChat(courtChatRoster);
                    }
                  }}
                />
                <div className="court-chat-actions">
                  {courtChatBusy ? (
                    <button className="court-chat-stop" disabled={!courtChatBusy} onClick={onStopCourtChat}>停止</button>
                  ) : (
                    <button className="court-chat-summary" disabled={!canChat || !courtChatLiveMessages.length} onClick={() => onSummarizeCourtChat(courtChatRoster)}>总结</button>
                  )}
                  <button className={`court-chat-send ${courtChatBusy ? "interrupt" : ""}`} disabled={!canChat || !courtChatInput.trim()} onClick={() => onSendCourtChat(courtChatRoster)}>
                    {courtChatBusy ? "打断" : "发送"}
                  </button>
                </div>
                {courtChatError ? <div className="court-chat-error">{courtChatError}</div> : null}
              </footer>
            </section>
          </>
        ) : null}
        {showHistory ? (
          <>
            <div className="court-chat-history-scrim" aria-hidden="true" />
            <div className="court-chat-history" role="dialog" aria-label="本月朝会聊天历史">
              <div className="court-chat-history-head">
                <b>本月朝会</b>
                <button className="icon-button" onClick={() => setShowHistory(false)} aria-label="关闭朝会历史"><X size={14} /></button>
              </div>
              <div className="court-chat-history-list">
                {courtChatHistory.length ? courtChatHistory.map((m, i) => (
                  <div key={`${m.speaker}-${i}-${m.content}`} className={`court-chat-line ${m.role}`}>
                    <strong>{m.speaker}</strong>
                    <span>{cleanCourtChatText(m.content)}</span>
                  </div>
                )) : <div className="court-chat-empty">本月尚无朝会奏对。</div>}
              </div>
            </div>
          </>
        ) : null}
        {courtChatStep === "composing" && courtChatAvailable ? (
        <div className="court-chat-dock open step-composing">
          {activeIssues.length ? (
            <div className="court-chat-topic-chips">
              <span className="court-chat-topic-chips-label">话题：</span>
              {activeIssues.map((issue) => (
                <button
                  key={issue.id}
                  type="button"
                  className="court-chat-topic-chip"
                  disabled={courtChatBusy}
                  title={issue.stage_text}
                  onClick={() => pickCourtChatTopic(issue)}
                >
                  {issue.title}
                </button>
              ))}
            </div>
          ) : null}
          {!courtChatPanelOpen ? (
            <>
              <button className="court-chat-history-btn" onClick={() => setShowHistory((v) => !v)} title="查看本月朝会聊天历史">
                <MessageSquareText size={16} />
                <span>{courtChatHistory.length}</span>
              </button>
              <textarea
                className="court-chat-input"
                value={courtChatInput}
                placeholder="垂询群臣..."
                rows={1}
                onChange={(e) => onCourtChatInputChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSendCourtChat(courtChatRoster);
                  }
                }}
              />
              <button className="court-chat-send" disabled={!canChat || !courtChatInput.trim()} onClick={() => onSendCourtChat(courtChatRoster)}>
                发问
              </button>
              {courtChatError ? <div className="court-chat-error">{courtChatError}</div> : null}
            </>
          ) : null}
        </div>
        ) : null}
      </aside>
    </>
  );
}

export function HaremDrawer({
  consorts,
  haremGroup,
  selectedMinister,
  open,
  onGroupChange,
  onClose,
  onOpenChat,
  onUploadPortrait,
}: {
  consorts: Minister[];
  haremGroup: string;
  selectedMinister: string;
  open: boolean;
  onGroupChange: (group: string) => void;
  onClose: () => void;
  onOpenChat: (minister: Minister) => void;
  onUploadPortrait: (ministerName: string, file: File) => Promise<void>;
}) {
  const [q, setQ] = React.useState("");
  const filtered = q ? consorts.filter((c) => c.name.includes(q)) : consorts;
  return (
    <>
      {open && <button className="drawer-scrim" aria-label="收起" onClick={onClose} />}
      <aside className={`court-drawer harem-drawer overlay-panel ${open ? "open" : ""}`}>
        <div className="drawer-brand">
          <div className="panel-title">
            <Crown size={17} />
            <span>后宫</span>
          </div>
          <button className="icon-button" aria-label="收起" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="segmented">
          {["全部", "收藏"].map((group) => (
            <button
              className={haremGroup === group ? "active" : ""}
              key={group}
              onClick={() => onGroupChange(group)}
            >
              {group}
            </button>
          ))}
        </div>
        <div className="right-drawer-search court-search">
          <input className="right-drawer-search-input" placeholder="搜索姓名…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <MinisterCardList
          list={filtered}
          portraitPrefix="consort_"
          selectedMinister={selectedMinister}
          emptyNote={q ? "无匹配结果。" : "后宫暂无可召见之人。"}
          onOpenChat={onOpenChat}
          onUploadPortrait={onUploadPortrait}
        />
      </aside>
    </>
  );
}
