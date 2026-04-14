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
  parseStatus: string;
  syncStatus: string;
};

export type StateItem = {
  id: string;
  title: string;
  body: string;
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
