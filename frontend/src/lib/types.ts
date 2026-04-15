export type ProjectSummary = {
  id: string;
  name: string;
  summary: string;
  status: string;
  scenarioType: string;
  updatedAt: string;
};

export type SourceRecord = {
  id: string;
  name: string;
  sourceKind: string;
  uploadKind?: string;
  storagePath?: string;
  normalizedPath?: string;
  parseStatus: string;
  parseSummary?: string;
  syncStatus: string;
};

export type StateItem = {
  id: string;
  title: string;
  body: string;
};

export type ArtifactRecord = {
  id: string;
  artifactType: string;
  title: string;
  summary: string;
  status: string;
  contentFormat: string;
  storagePath?: string;
};

export type ChatEvent = {
  event: string;
  data: Record<string, unknown>;
};

export type ProjectState = {
  currentUnderstanding: StateItem[];
  pendingItems: StateItem[];
  confirmedItems: StateItem[];
  conflictItems: StateItem[];
  mvpItems: StateItem[];
  versions: StateItem[];
  artifacts: StateItem[];
};
