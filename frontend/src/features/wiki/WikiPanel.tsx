import { useEffect, useState } from 'react';

import { getWikiPage, getWikiRecord, listWikiPages } from '../../lib/api';
import type { WikiPage, WikiPageMeta, WikiRecord } from '../../lib/types';

type Props = {
  projectId: string;
  onSourceClick?: (sourceId: string) => void;
};

export function WikiPanel({ projectId, onSourceClick }: Props) {
  const [record, setRecord] = useState<WikiRecord | null>(null);
  const [pages, setPages] = useState<WikiPageMeta[]>([]);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<WikiPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getWikiRecord(projectId), listWikiPages(projectId)])
      .then(([rec, pageList]) => {
        if (cancelled) return;
        setRecord(rec);
        setPages(pageList);
        const firstSlug = pageList[0]?.slug ?? null;
        setActiveSlug(firstSlug);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : '加载 wiki 失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    if (!activeSlug) {
      setActivePage(null);
      return;
    }
    let cancelled = false;
    getWikiPage(projectId, activeSlug)
      .then((page) => {
        if (!cancelled) setActivePage(page);
      })
      .catch((exc: unknown) => {
        if (!cancelled)
          setError(exc instanceof Error ? exc.message : '加载 wiki 页面失败');
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, activeSlug]);

  if (loading) {
    return <div className="p-4 text-sm text-muted-foreground">加载 wiki...</div>;
  }

  if (error) {
    return <div className="p-4 text-sm text-destructive">{error}</div>;
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3 text-sm">
      <div className="rounded-md border bg-muted/40 p-2 text-xs">
        <div className="font-medium">项目 wiki</div>
        <div className="text-muted-foreground">
          页面 {record?.page_count ?? 0} 个 · 最近维护{' '}
          {record?.last_maintained_at ?? '未维护'}
          {record?.pending_source_ids?.length
            ? ` · 等待维护 ${record.pending_source_ids.length} 条 source`
            : ''}
        </div>
        <div className="mt-1 text-[10px] text-muted-foreground">
          wiki 是综合理解层，不是 citation 来源；正式引用走 query_project_evidence。
        </div>
      </div>
      <div className="flex flex-1 gap-3 overflow-hidden">
        <ul className="w-44 shrink-0 space-y-1 overflow-y-auto border-r pr-2">
          {pages.map((page) => (
            <li key={page.slug}>
              <button
                type="button"
                className={`w-full rounded px-2 py-1 text-left text-xs hover:bg-muted ${
                  page.slug === activeSlug ? 'bg-muted font-medium' : ''
                }`}
                onClick={() => setActiveSlug(page.slug)}
              >
                <div className="truncate">{page.title}</div>
                <div className="text-[10px] text-muted-foreground">{page.kind}</div>
              </button>
            </li>
          ))}
          {!pages.length ? (
            <li className="px-2 py-1 text-xs text-muted-foreground">
              当前还没有 wiki 页面。
            </li>
          ) : null}
        </ul>
        <div className="flex-1 overflow-y-auto">
          {activePage ? (
            <article className="space-y-2">
              <header className="space-y-1">
                <h3 className="text-base font-semibold">{activePage.title}</h3>
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                  <span className="rounded bg-muted px-1.5 py-0.5">
                    kind={activePage.kind}
                  </span>
                  {activePage.source_ids.map((sid) => (
                    <button
                      key={sid}
                      type="button"
                      className="rounded border bg-background px-1.5 py-0.5 hover:bg-muted"
                      onClick={() => onSourceClick?.(sid)}
                      title="跳转到对应 source"
                    >
                      src: {sid}
                    </button>
                  ))}
                  {activePage.last_maintained_at ? (
                    <span className="text-[10px]">
                      maintained={activePage.last_maintained_at}
                      {activePage.last_maintained_by
                        ? ` by ${activePage.last_maintained_by}`
                        : ''}
                    </span>
                  ) : null}
                </div>
              </header>
              <pre className="whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-xs leading-relaxed">
                {activePage.body}
              </pre>
            </article>
          ) : (
            <div className="text-xs text-muted-foreground">选择左侧页面查看内容。</div>
          )}
        </div>
      </div>
    </div>
  );
}
