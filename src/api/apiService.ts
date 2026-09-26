import * as vscode from "vscode";
import axios from "axios";
import {
  CodeContext,
  ExplanationMode,
  ExplanationResponse,
  WhyResponse,
  RelationsResponse,
  DataFlowResponse,
  HistoryResponse,
  ImpactResponse,
  TestsResponse,
  DebugResponse,
  ArchitectureResponse,
} from "../types";
import * as mock from "./mockService";

function backendUrl(): string {
  return vscode.workspace
    .getConfiguration("aicode")
    .get<string>("backendUrl", "http://localhost:3000");
}

function useMock(): boolean {
  return vscode.workspace
    .getConfiguration("aicode")
    .get<boolean>("useMockData", true);
}

async function post<T>(path: string, body: object): Promise<T> {
  const url = `${backendUrl()}${path}`;
  const res = await axios.post<T>(url, body, { timeout: 30000 });
  return res.data;
}

async function get<T>(path: string): Promise<T> {
  const url = `${backendUrl()}${path}`;
  const res = await axios.get<T>(url, { timeout: 30000 });
  return res.data;
}

// ─────────────────────────────────────────────────────────────────────────────

export async function explainCode(
  ctx: CodeContext,
  mode: ExplanationMode
): Promise<ExplanationResponse> {
  if (useMock()) {
    return mock.mockExplain(ctx, mode);
  }
  return post<ExplanationResponse>("/explanations/code", { ...ctx, mode });
}

export async function explainWhy(ctx: CodeContext): Promise<WhyResponse> {
  if (useMock()) {
    return mock.mockWhy(ctx);
  }
  return post<WhyResponse>("/explanations/why", ctx);
}

export async function getRelations(ctx: CodeContext): Promise<RelationsResponse> {
  if (useMock()) {
    return mock.mockRelations(ctx);
  }
  return post<RelationsResponse>("/relations/analyze", ctx);
}

export async function traceDataFlow(ctx: CodeContext): Promise<DataFlowResponse> {
  if (useMock()) {
    return mock.mockDataFlow(ctx);
  }
  return post<DataFlowResponse>("/dataflow/trace", ctx);
}

export async function getHistory(ctx: CodeContext): Promise<HistoryResponse> {
  if (useMock()) {
    return mock.mockHistory(ctx);
  }
  return post<HistoryResponse>("/history/analyze", ctx);
}

export async function analyzeImpact(ctx: CodeContext): Promise<ImpactResponse> {
  if (useMock()) {
    return mock.mockImpact(ctx);
  }
  return post<ImpactResponse>("/impact/analyze", ctx);
}

export async function findTests(ctx: CodeContext): Promise<TestsResponse> {
  if (useMock()) {
    return mock.mockTests(ctx);
  }
  return post<TestsResponse>("/tests/related", ctx);
}

export async function debugError(
  ctx: CodeContext,
  error?: string
): Promise<DebugResponse> {
  if (useMock()) {
    return mock.mockDebug(ctx, error);
  }
  return post<DebugResponse>("/debug/analyze", { ...ctx, error });
}

export async function getArchitecture(
  repositoryId?: string
): Promise<ArchitectureResponse> {
  if (useMock()) {
    return mock.mockArchitecture();
  }
  const path = repositoryId
    ? `/architecture/${repositoryId}`
    : "/architecture/current";
  return get<ArchitectureResponse>(path);
}
