import React from "react";
import type { LoadingState } from "../store/appStore";
import { CapabilityNotice } from "./CapabilityNotice";
import { LoadingSpinner, ErrorState, EmptyState } from "./States";

interface GateProps {
  status: LoadingState;
  error?: string;
  unavailable?: boolean;
  unavailableMessage?: string;
  useMock?: boolean;
  loadingMessage?: string;
  errorFallback: string;
  idleMessage: string;
  /**
   * True when the payload came from the real backend. Mock-mode results are
   * labelled as demo data; real results are not, so the notice never appears
   * over genuine backend output.
   */
  fromBackend?: boolean;
}

/**
 * Renders the non-success states for a tab in one place.
 *
 * Returns null once the tab has a result, so each feature tab declares its
 * happy path without repeating the loading/error/empty/unavailable ladder.
 * Keeping "unavailable" separate from "error" is the point: a backend feature
 * that does not exist must not look like a request that failed.
 */
export function TabGate({
  status,
  error,
  unavailable,
  unavailableMessage,
  useMock,
  loadingMessage,
  errorFallback,
  idleMessage,
  fromBackend,
}: GateProps) {
  if (unavailable) {
    return <CapabilityNotice unavailable message={unavailableMessage} />;
  }

  if (status === "loading") {
    return <LoadingSpinner message={loadingMessage} />;
  }

  if (status === "error") {
    return <ErrorState message={error ?? errorFallback} />;
  }

  if (status === "idle") {
    return <EmptyState message={idleMessage} />;
  }

  if (status === "success" && useMock && !fromBackend) {
    return <CapabilityNotice useMock />;
  }

  return null;
}
