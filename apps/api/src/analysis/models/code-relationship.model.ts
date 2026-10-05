export enum RelationshipKind {
  Calls = 'calls',
  Imports = 'imports',
  Extends = 'extends',
  Implements = 'implements',
  References = 'references',
  Instantiates = 'instantiates',
  Contains = 'contains',
}

export interface CodeRelationship {
  id: string;
  fromSymbolId: string;
  toSymbolId: string;
  kind: RelationshipKind;
  filePath: string;
  line: number;
}
