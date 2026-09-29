export type Row = Record<string, unknown>;

export interface RowDiff {
  key: string;
  main: Row | null;
  fork: Row | null;
}

/** Rows that differ between two result sets, matched on `key`. Both sides must
 *  come from the same SELECT so column order (and thus JSON) is comparable. */
export function diffRows(main: Row[], fork: Row[], key: string): RowDiff[] {
  const m = new Map(main.map((r) => [String(r[key]), r]));
  const f = new Map(fork.map((r) => [String(r[key]), r]));
  const keys = [...new Set([...m.keys(), ...f.keys()])].sort();
  return keys.flatMap((k) => {
    const a = m.get(k) ?? null;
    const b = f.get(k) ?? null;
    return JSON.stringify(a) === JSON.stringify(b) ? [] : [{ key: k, main: a, fork: b }];
  });
}
