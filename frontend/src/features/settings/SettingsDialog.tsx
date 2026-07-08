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
import { getLlmSettings, updateLlmSettings } from '../../lib/api';

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
  const [apiFormat, setApiFormat] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setSaved(false);
    getLlmSettings()
      .then((settings) => {
        setApiKey('');
        setApiKeyPreview(settings.api_key_preview);
        setApiKeyConfigured(settings.api_key_configured);
        setBaseUrl(settings.base_url);
        setModel(settings.model);
        setApiFormat(settings.api_format);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [open]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateLlmSettings({
        api_key: apiKey.trim() ? apiKey : undefined,
        base_url: baseUrl,
        model,
        api_format: apiFormat,
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
            LLM 接口配置,修改后立即生效并写入 .env.local。
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
              <label className="text-xs font-medium text-olive">LLM_API_KEY</label>
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
              <label className="text-xs font-medium text-olive">LLM_BASE_URL</label>
              <Input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.anthropic.com"
                className="font-mono text-sm"
              />
            </div>

            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-olive">LLM_MODEL</label>
              <Input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="claude-sonnet-4-5-20250929"
                className="font-mono text-sm"
              />
            </div>

            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-olive">LLM_API_FORMAT</label>
              <div className="flex gap-1 rounded-lg border border-[#d4cab0] bg-[#f5f1e6] p-1">
                {(['anthropic', 'openai'] as const).map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => setApiFormat(fmt)}
                    className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      apiFormat === fmt
                        ? 'bg-white text-olive shadow-sm'
                        : 'text-muted hover:text-olive'
                    }`}
                  >
                    {fmt === 'anthropic' ? 'Anthropic' : 'OpenAI'}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted">
                留空或选择接口格式;未指定时按 base_url 自动判断。
              </p>
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
