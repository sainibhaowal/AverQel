"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipState {
  label: string;
  left: number;
  top: number;
  above: boolean;
}

const TOOLTIP_SELECTOR = "[data-averqel-tooltip]";
const SKIP_TITLE_TAGS = new Set(["TITLE"]);
const TOOLTIP_DELAY_MS = 350;
const MAX_TOOLTIP_WIDTH = 320;
const pendingManagedTitleRemovals = new WeakSet<Element>();

function removeNativeTitleAttribute(element: Element) {
  pendingManagedTitleRemovals.add(element);
  element.removeAttribute("title");
}

function clearManagedTitle(element: Element) {
  const managedLabel = element.getAttribute("data-averqel-tooltip");
  if (element.getAttribute("data-averqel-native-title") !== "true") return;

  element.removeAttribute("data-averqel-native-title");
  element.removeAttribute("data-averqel-tooltip");

  if (element.getAttribute("data-averqel-managed-description") === managedLabel) {
    element.removeAttribute("aria-description");
    element.removeAttribute("data-averqel-managed-description");
  }
  if (element.getAttribute("data-averqel-managed-label") === managedLabel) {
    element.removeAttribute("aria-label");
    element.removeAttribute("data-averqel-managed-label");
  }
}

function removeManagedTooltipDescription(element: Element | null) {
  if (element?.getAttribute("data-averqel-managed-describedby") !== "true") return;
  const remainingIds = (element.getAttribute("aria-describedby") ?? "")
    .split(/\s+/)
    .filter((id) => id && id !== "averqel-app-tooltip");
  if (remainingIds.length) element.setAttribute("aria-describedby", remainingIds.join(" "));
  else element.removeAttribute("aria-describedby");
  element.removeAttribute("data-averqel-managed-describedby");
}

function preserveTitleDescription(element: Element, label: string) {
  const managedLabel = element.getAttribute("data-averqel-managed-label");
  const currentLabel = element.getAttribute("aria-label");
  const needsTitleAsAccessibleName = element.matches(
    "button, a, [role='button'], iframe, frame, object, embed, img",
  );
  const hasVisibleAccessibleName =
    Boolean(element.textContent?.trim()) ||
    element.matches("img[alt]:not([alt=''])") ||
    Boolean(element.querySelector("img[alt]:not([alt='']), svg[aria-label]"));
  const hasExplicitAccessibleName =
    element.hasAttribute("aria-labelledby") ||
    (Boolean(currentLabel) && currentLabel !== managedLabel);
  const useTitleAsAccessibleName =
    needsTitleAsAccessibleName &&
    !hasVisibleAccessibleName &&
    !hasExplicitAccessibleName &&
    (!currentLabel || currentLabel === managedLabel);

  const managedDescription = element.getAttribute("data-averqel-managed-description");
  const currentDescription = element.getAttribute("aria-description");
  if (useTitleAsAccessibleName) {
    if (currentDescription === managedDescription) {
      element.removeAttribute("aria-description");
      element.removeAttribute("data-averqel-managed-description");
    }
    element.setAttribute("aria-label", label);
    element.setAttribute("data-averqel-managed-label", label);
  } else {
    if (!currentDescription || currentDescription === managedDescription) {
      element.setAttribute("aria-description", label);
      element.setAttribute("data-averqel-managed-description", label);
    }
    if (currentLabel && currentLabel === managedLabel) {
      element.removeAttribute("aria-label");
      element.removeAttribute("data-averqel-managed-label");
    }
  }
}

function moveNativeTitleToTooltip(element: Element) {
  if (SKIP_TITLE_TAGS.has(element.tagName)) return;

  const title = element.getAttribute("title");
  if (title === null) return;

  const label = title.trim();
  if (!label) {
    removeNativeTitleAttribute(element);
    clearManagedTitle(element);
    return;
  }

  preserveTitleDescription(element, label);
  if (element.matches(".ui-tooltip[data-tooltip]:not([data-tooltip=''])")) {
    clearManagedTitle(element);
    removeNativeTitleAttribute(element);
    return;
  }

  element.setAttribute("data-averqel-tooltip", label);
  element.setAttribute("data-averqel-native-title", "true");
  removeNativeTitleAttribute(element);
}

function normalizeTitles(root: ParentNode) {
  if (root instanceof Element) moveNativeTitleToTooltip(root);
  root.querySelectorAll("[title]").forEach(moveNativeTitleToTooltip);
}

function findTooltipTrigger(target: EventTarget | null) {
  return target instanceof Element ? target.closest(TOOLTIP_SELECTOR) : null;
}

function getTooltipState(anchor: Element, label: string): TooltipState {
  const bounds = anchor.getBoundingClientRect();
  const tooltipWidth = Math.min(MAX_TOOLTIP_WIDTH, window.innerWidth - 16);
  const halfWidth = tooltipWidth / 2;
  const left = Math.max(
    halfWidth + 8,
    Math.min(window.innerWidth - halfWidth - 8, bounds.left + bounds.width / 2),
  );
  const above = bounds.top > 96;

  return {
    label,
    left,
    top: above ? bounds.top - 8 : bounds.bottom + 8,
    above,
  };
}

export default function AppTooltipLayer() {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const timerRef = useRef<number | null>(null);
  const activeAnchorRef = useRef<Element | null>(null);

  useEffect(() => {
    const clearTimer = () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const hideTooltip = () => {
      clearTimer();
      removeManagedTooltipDescription(activeAnchorRef.current);
      activeAnchorRef.current = null;
      setTooltip(null);
    };

    const showTooltip = (anchor: Element, delay: number) => {
      const label = anchor.getAttribute("data-averqel-tooltip")?.trim();
      if (!label) return;
      if (activeAnchorRef.current === anchor && (delay > 0 || timerRef.current === null)) return;
      if (activeAnchorRef.current && activeAnchorRef.current !== anchor) hideTooltip();

      clearTimer();
      activeAnchorRef.current = anchor;
      setTooltip(null);
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        if (anchor.isConnected) {
          setTooltip(getTooltipState(anchor, label));
          const describedBy =
            anchor.getAttribute("aria-describedby")?.split(/\s+/).filter(Boolean) ?? [];
          if (!describedBy.includes("averqel-app-tooltip")) {
            anchor.setAttribute(
              "aria-describedby",
              [...describedBy, "averqel-app-tooltip"].join(" "),
            );
            anchor.setAttribute("data-averqel-managed-describedby", "true");
          }
        }
      }, delay);
    };

    const onPointerOver = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const anchor = findTooltipTrigger(event.target);
      if (anchor) showTooltip(anchor, TOOLTIP_DELAY_MS);
    };

    const onPointerOut = (event: PointerEvent) => {
      const anchor = findTooltipTrigger(event.target);
      if (!anchor || anchor !== activeAnchorRef.current) return;
      if (event.relatedTarget instanceof Node && anchor.contains(event.relatedTarget)) return;
      if (document.activeElement === anchor) return;
      hideTooltip();
    };

    const onFocusIn = (event: FocusEvent) => {
      const anchor = findTooltipTrigger(event.target);
      if (anchor) showTooltip(anchor, 0);
    };

    const onFocusOut = (event: FocusEvent) => {
      const anchor = findTooltipTrigger(event.target);
      if (!anchor || anchor !== activeAnchorRef.current) return;
      if (event.relatedTarget instanceof Node && anchor.contains(event.relatedTarget)) return;
      hideTooltip();
    };

    const onPointerDown = (event: PointerEvent) => {
      const anchor = findTooltipTrigger(event.target);
      if (anchor && anchor === activeAnchorRef.current) hideTooltip();
    };

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "attributes" && mutation.target instanceof Element) {
          if (
            !mutation.target.hasAttribute("title") &&
            pendingManagedTitleRemovals.has(mutation.target)
          ) {
            pendingManagedTitleRemovals.delete(mutation.target);
          } else if (!mutation.target.hasAttribute("title")) {
            clearManagedTitle(mutation.target);
          } else {
            moveNativeTitleToTooltip(mutation.target);
          }
        }
        mutation.addedNodes.forEach((node) => {
          if (node instanceof Element) normalizeTitles(node);
        });
      }

      const activeAnchor = activeAnchorRef.current;
      if (!activeAnchor) return;
      if (!activeAnchor.isConnected) hideTooltip();
      else {
        const label = activeAnchor.getAttribute("data-averqel-tooltip")?.trim();
        if (!label) hideTooltip();
        else setTooltip((current) => (current ? getTooltipState(activeAnchor, label) : current));
      }
    });

    normalizeTitles(document.documentElement);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["title"],
      childList: true,
      subtree: true,
    });
    document.addEventListener("pointerover", onPointerOver);
    document.addEventListener("pointerout", onPointerOut);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);

    return () => {
      observer.disconnect();
      clearTimer();
      removeManagedTooltipDescription(activeAnchorRef.current);
      activeAnchorRef.current = null;
      document.removeEventListener("pointerover", onPointerOver);
      document.removeEventListener("pointerout", onPointerOut);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  useEffect(() => {
    if (!tooltip) return;

    const syncPosition = () => {
      const activeAnchor = activeAnchorRef.current;
      const label = activeAnchor?.getAttribute("data-averqel-tooltip")?.trim();
      if (activeAnchor?.isConnected && label) setTooltip(getTooltipState(activeAnchor, label));
      else setTooltip(null);
    };

    window.addEventListener("resize", syncPosition);
    window.addEventListener("scroll", syncPosition, true);
    return () => {
      window.removeEventListener("resize", syncPosition);
      window.removeEventListener("scroll", syncPosition, true);
    };
  }, [tooltip]);

  if (!tooltip || typeof document === "undefined") return null;

  return createPortal(
    <div
      id="averqel-app-tooltip"
      role="tooltip"
      className="averqel-tooltip-surface pointer-events-none fixed z-[10000] max-h-[min(60dvh,24rem)] max-w-[min(20rem,calc(100vw-1rem))] overflow-y-auto px-3 py-2 text-left text-xs leading-5 font-medium break-words"
      style={{
        top: tooltip.top,
        left: tooltip.left,
        transform: `translate(-50%, ${tooltip.above ? "-100%" : "0"})`,
      }}
    >
      {tooltip.label}
    </div>,
    document.body,
  );
}
