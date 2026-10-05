import 'reflect-metadata';
import { DependencyPathService } from './dependency-path.service.js';
import { CodeSymbol, SymbolKind } from '../../analysis/models/code-symbol.model.js';
import {
  CodeRelationship,
  RelationshipKind,
} from '../../analysis/models/code-relationship.model.js';

function sym(id: string, name: string, file = 'src/a.ts'): CodeSymbol {
  return {
    id,
    name,
    kind: SymbolKind.Method,
    location: {
      filePath: file,
      startLine: 1,
      endLine: 5,
      startColumn: 0,
      endColumn: 0,
    },
  };
}

function rel(from: string, to: string, kind = RelationshipKind.Calls): CodeRelationship {
  return {
    id: `${from}->${to}:${kind}`,
    fromSymbolId: from,
    toSymbolId: to,
    kind,
    filePath: 'src/a.ts',
    line: 1,
  };
}

let service: DependencyPathService;

beforeEach(() => {
  service = new DependencyPathService();
});

it('traces an ordered dependency path', () => {
  const symbols = [
    sym('1', 'AuthController.login', 'src/auth/auth.controller.ts'),
    sym('2', 'AuthService.login', 'src/auth/auth.service.ts'),
    sym('3', 'UserRepository.findByEmail', 'src/users/user.repository.ts'),
    sym('4', 'JwtService.sign', 'src/auth/jwt.service.ts'),
  ];
  const relationships = [
    rel('1', '2'),
    rel('2', '3'),
    rel('2', '4'),
  ];
  const path = service.trace('1', symbols, relationships);
  expect(path.nodes.map((n) => n.symbolName)).toEqual([
    'AuthController.login',
    'AuthService.login',
    'UserRepository.findByEmail',
    'JwtService.sign',
  ]);
  expect(path.edges).toHaveLength(3);
  expect(path.truncated).toBe(false);
  expect(path.nodes[0].filePath).toBe('src/auth/auth.controller.ts');
});

it('stops on cycles without revisiting nodes', () => {
  const symbols = [sym('1', 'A.ping'), sym('2', 'B.pong')];
  const relationships = [rel('1', '2'), rel('2', '1')];
  const path = service.trace('1', symbols, relationships);
  expect(path.nodes.map((n) => n.symbolId)).toEqual(['1', '2']);
  expect(path.edges).toHaveLength(1);
});

it('respects the max depth', () => {
  const symbols = [sym('1', 'a'), sym('2', 'b'), sym('3', 'c'), sym('4', 'd')];
  const relationships = [rel('1', '2'), rel('2', '3'), rel('3', '4')];
  const path = service.trace('1', symbols, relationships, 1);
  expect(path.nodes.length).toBeLessThanOrEqual(2);
  expect(path.truncated).toBe(true);
});

it('returns empty result for an unknown symbol', () => {
  const path = service.trace('missing', [], []);
  expect(path.nodes).toEqual([]);
  expect(path.edges).toEqual([]);
});

it('does not invent edges to file-level import targets', () => {
  const symbols = [sym('1', 'A.run')];
  const relationships = [
    rel('1', 'src/auth/auth.service', RelationshipKind.Imports),
  ];
  const path = service.trace('1', symbols, relationships);
  expect(path.nodes).toHaveLength(1);
  expect(path.edges).toHaveLength(0);
});
