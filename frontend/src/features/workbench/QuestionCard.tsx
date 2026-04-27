import { useMemo, useState } from 'react';
import { CheckCircle2, HelpCircle, Loader2 } from 'lucide-react';

import { Button } from '../../components/ui/button';
import { Textarea } from '../../components/ui/textarea';
import { cn } from '../../lib/utils';
import type { PendingQuestion } from '../../lib/types';

type QuestionCardProps = {
  question: PendingQuestion;
  onSubmit: (
    questionId: string,
    payload: { selected_labels: string[]; free_text: string | null }
  ) => Promise<void>;
};

export function QuestionCard({ question, onSubmit }: QuestionCardProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [otherChecked, setOtherChecked] = useState(false);
  const [otherText, setOtherText] = useState('');

  const isAnswered = question.status === 'answered';
  const isTimedOut = question.status === 'timed_out';
  const isSubmitting = question.status === 'submitting';
  const isInteractive = question.status === 'pending';

  const answeredLabels = useMemo(() => question.selected_labels ?? [], [question.selected_labels]);
  const answeredFreeText = question.free_text ?? null;

  const toggleOption = (label: string) => {
    if (!isInteractive) return;
    setSelected((prev) => {
      if (question.multi_select) {
        return prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label];
      }
      return prev[0] === label ? [] : [label];
    });
  };

  const submit = async (overrideLabels?: string[]) => {
    if (isSubmitting || !isInteractive) return;
    const finalLabels = overrideLabels ?? selected;
    const finalFree = otherChecked ? otherText.trim() : '';
    if (finalLabels.length === 0 && !finalFree) return;
    await onSubmit(question.question_id, {
      selected_labels: finalLabels,
      free_text: finalFree ? finalFree : null,
    });
  };

  const onOptionClick = (label: string) => {
    if (!isInteractive) return;
    if (question.multi_select) {
      toggleOption(label);
      return;
    }
    if (otherChecked) {
      setSelected([label]);
      return;
    }
    void submit([label]);
  };

  const canSubmit =
    isInteractive &&
    (selected.length > 0 || (otherChecked && otherText.trim().length > 0));

  return (
    <div
      className={cn(
        'mt-3 rounded-[18px] border bg-ivory/85 px-3.5 py-3.5 shadow-sm',
        isAnswered || isTimedOut
          ? 'border-borderCream'
          : 'border-[#d8c8a8]'
      )}
    >
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
        <HelpCircle className="h-3.5 w-3.5" />
        <span>{question.header ?? '请你做个选择'}</span>
        {question.multi_select ? <span className="text-[10px] text-muted/80">多选</span> : null}
        {isAnswered ? <span className="text-[10px] text-[#3d6b50]">已回答</span> : null}
        {isTimedOut ? <span className="text-[10px] text-[#9a2a2a]">已超时</span> : null}
      </div>
      <div className="mt-2 text-sm leading-6 text-nearBlack whitespace-pre-wrap">
        {question.question}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {question.options.map((option) => {
          const isPicked = isInteractive
            ? selected.includes(option.label)
            : answeredLabels.includes(option.label);
          return (
            <button
              key={option.label}
              type="button"
              disabled={!isInteractive}
              onClick={() => onOptionClick(option.label)}
              className={cn(
                'flex max-w-full flex-col items-start gap-0.5 rounded-[12px] border px-3 py-2 text-left text-sm transition',
                isPicked
                  ? 'border-terracotta bg-accentSoft/70 text-nearBlack shadow-[0_0_0_1px_rgba(201,100,66,0.35)]'
                  : 'border-line bg-ivory text-nearBlack hover:border-[#caa97a] hover:bg-sand/40',
                !isInteractive && 'cursor-default opacity-90'
              )}
            >
              <span className="font-medium">{option.label}</span>
              {option.description ? (
                <span className="text-[12px] leading-5 text-muted">{option.description}</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {isInteractive ? (
        <div className="mt-3 flex flex-col gap-2">
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={otherChecked}
              onChange={(event) => setOtherChecked(event.target.checked)}
              className="h-3.5 w-3.5 rounded border-line accent-terracotta"
            />
            <span>其他 / 补充说明</span>
          </label>
          {otherChecked ? (
            <Textarea
              value={otherText}
              onChange={(event) => setOtherText(event.target.value)}
              placeholder="把你的想法直接写在这里..."
              className="min-h-[64px] resize-none text-sm"
            />
          ) : null}
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              size="sm"
              disabled={!canSubmit || isSubmitting}
              onClick={() => void submit()}
              className="gap-1.5"
            >
              {isSubmitting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )}
              提交
            </Button>
          </div>
        </div>
      ) : null}

      {isAnswered && answeredFreeText ? (
        <div className="mt-3 rounded-[12px] border border-line bg-ivory/70 px-3 py-2 text-xs leading-5 text-muted">
          <div className="font-medium uppercase tracking-[0.14em] text-[10px] text-muted/80">
            补充说明
          </div>
          <div className="mt-1 whitespace-pre-wrap text-nearBlack">{answeredFreeText}</div>
        </div>
      ) : null}
    </div>
  );
}
