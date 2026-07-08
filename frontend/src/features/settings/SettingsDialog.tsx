import { useEffect, useState } from 'react';
import { Eye, EyeOff, Loader2, Save } from 'lucide-react';

import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';
import { Input } from '../../components/ui/input';
import { getClaudeSettings, updateClaudeSettings } from '../../lib/api';

type SettingsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [apiKeyPreview, setApiKeyPreview] = useState('');
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSaved(false);
    getClaudeSettings()
      .then((settings) => {
        setApiKey('');
        setApiKeyPreview(settings.api_key_preview);
        setApiKeyConfigured(settings.api_key_configured);
        setBaseUrl(settings.base_url);
        setModel(settings.model);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [open]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateClaudeSettings({
        api_key: apiKey.trim() ? apiKey : undefined,
        base_url: baseUrl,
        model,
      });
      setSaved(true);
      setTimeout(() => onOpenChange(false), 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败。');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(520px,92vw)] gap-5">
        <DialogHeader>
          <DialogTitle>Provider 设置</DialogTitle>
          <DialogDescription>
            Claude Agent SDK 接口配置,修改后立即生效并写入 .env.local。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载当前配置…
          </div>
        ) : (
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-olive">ANTHROPIC_API_KEY</label>
              <div className="flex gap-2">
                <Input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={
                    apiKeyConfigured
                      ? `已配置 ${apiKeyPreview}，留空不修改`
                      : 'sk-...'
                  }
                  className="font-mono text-sm"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0"
                  aria-label={showKey ? '隐藏密钥' : '显示密钥'}
                  onClick={() => setShowKey((v) => !v)}
                >
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-olive">ANTHROPIC_BASE_URL</label>
              <Input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.anthropic.com"
                className="font-mono text-sm"
              />
            </div>

            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-olive">CLAUDE_MODEL</label>
              <Input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="claude-sonnet-4-5-20250929"
                className="font-mono text-sm"
              />
            </div>

            {error && (
              <div className="rounded-[10px] border border-[#e3c8c4] bg-[#fbeeec] px-3 py-2 text-xs text-errorWarm">
                {error}
              </div>
            )}
            {saved && (
              <div className="rounded-[10px] border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700">
                已保存,下次请求即生效。
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? (
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-1.5 h-4 w-4" />
                )}
                保存
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
