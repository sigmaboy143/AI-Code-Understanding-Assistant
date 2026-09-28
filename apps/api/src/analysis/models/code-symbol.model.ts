export enum SymbolKind {
  Function = 'function',
  Class = 'class',
  Method = 'method',
  Variable = 'variable',
  Interface = 'interface',
  Type = 'type',
  Enum = 'enum',
  Module = 'module',
}

export interface SymbolLocation {
  filePath: string;
  startLine: number;
  endLine: number;
  startColumn: number;
  endColumn: number;
}

export interface CodeSymbol {
  id: string;
  name: string;
  kind: SymbolKind;
  location: SymbolLocation;
  signature?: string;
  documentation?: string;
}
